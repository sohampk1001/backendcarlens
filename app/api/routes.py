import uuid
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.models.schemas import (
    VehicleDetails, AnalysisRequest, AnalysisResult,
    DealScore, PriceEstimate, OwnershipCost, RiskSignal,
    ComparableVehicle, NegotiationRange, ImageAnalysis,
    SavedVehicle, ComparisonRequest, ComparisonResult,
    ComparisonItem, Recommendation
)
from app.services import groq_service, gemini_service, analysis_engine
from app.services.market_data import get_market_context_summary, get_demand_score, is_high_demand

router = APIRouter(prefix="/api", tags=["analysis"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "CARVIEW_AI Backend",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "groq_available": groq_service._groq_available,
        "gemini_available": gemini_service._genai_configured
    }


def _enrich_from_ai_extract(vehicle: VehicleDetails, description: Optional[str], url: Optional[str]) -> VehicleDetails:
    current = vehicle.model_dump()
    if url and not current.get("listing_url"):
        current["listing_url"] = url
    if description and not current.get("seller_description"):
        current["seller_description"] = description
    vehicle = VehicleDetails(**current)

    if not description and not vehicle.seller_description and not url:
        return vehicle

    desc_to_use = description or vehicle.seller_description or ""
    try:
        extracted = groq_service.extract_listing_data(desc_to_use, url)
        if extracted:
            current = vehicle.model_dump()
            for key, val in extracted.items():
                if val is not None and key in VehicleDetails.model_fields and (
                    current.get(key) is None or current.get(key) == ""
                ):
                    current[key] = val
            vehicle = VehicleDetails(**current)
    except Exception as e:
        logger.warning(f"AI extraction enrich failed: {e}")
    return vehicle


def _fill_defaults(vehicle: VehicleDetails) -> VehicleDetails:
    """Only fill fields that are completely missing — never overwrite user-provided data."""
    data = vehicle.model_dump()
    # Only apply safe fallbacks for non-critical fields
    safe_defaults = {
        "fuel_type": "Petrol",
        "transmission": "Manual",
        "ownership": "First Owner",
        "color": "Not specified",
        "body_type": "Unknown",
        "insurance_valid": "Unknown",
        "rto": "",
        "seller_description": "",
        "listing_url": None,
    }
    for k, v in safe_defaults.items():
        if data.get(k) is None or (isinstance(data.get(k), str) and data[k].strip() == ""):
            data[k] = v
    # Critical fields — only fill if both brand AND model are missing (completely blank submission)
    if not data.get("brand") and not data.get("model"):
        data["brand"] = "Unknown"
        data["model"] = "Unknown"
    if not data.get("location"):
        data["location"] = "India"
    return VehicleDetails(**data)


def _merge_identified_from_images(vehicle: VehicleDetails, image_results: List[Dict[str, Any]]) -> VehicleDetails:
    data = vehicle.model_dump()
    field_map = {
        "brand": "brand",
        "model": "model",
        "variant": "variant",
        "manufacturing_year": "manufacturing_year",
        "color": "color",
        "body_type": "body_type",
    }
    for result in image_results or []:
        ident = result.get("identified_vehicle") or {}
        for src, dest in field_map.items():
            val = ident.get(src)
            if val in (None, "", 0):
                continue
            current = data.get(dest)
            if current in (None, "", "Unknown", "Not specified"):
                data[dest] = val
    return VehicleDetails(**data)


@router.post("/analyze", response_model=AnalysisResult)
async def analyze_full_pipeline(request: AnalysisRequest):
    try:
        vehicle = request.vehicle_details or VehicleDetails()
        vehicle = _enrich_from_ai_extract(vehicle, request.description, request.listing_url)
        vehicle = _fill_defaults(vehicle)

        images_b64 = request.images or []
        desc = request.description or vehicle.seller_description

        # Inject market context into description for better AI analysis
        market_ctx = get_market_context_summary()
        demand = get_demand_score(vehicle.brand or '', vehicle.model or '')
        high_demand = is_high_demand(vehicle.model or '')
        enriched_desc = (
            f"{desc}\n\n"
            f"[Market Context: {market_ctx} "
            f"Demand score for {vehicle.brand} {vehicle.model}: {demand}/100. "
            f"{'High demand model — expect stronger resale value.' if high_demand else 'Moderate demand model.'}"
            f"]"
        )

        pipeline_result = analysis_engine.run_full_pipeline(
            vehicle=vehicle,
            images_b64=images_b64,
            description=enriched_desc,
            listing_url=request.listing_url
        )

        return AnalysisResult(**pipeline_result)

    except Exception as e:
        logger.exception(f"Full analysis pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/analyze/listing")
async def analyze_listing_only(
    listing_url: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    manual_details: Optional[str] = Form(None)
):
    try:
        vehicle = VehicleDetails()
        if manual_details:
            try:
                data = json.loads(manual_details)
                vehicle = VehicleDetails(**data)
            except Exception as pe:
                logger.warning(f"Could not parse manual_details JSON: {pe}")

        if listing_url and not description:
            from app.services.listing_fetch import fetch_listing_text
            description = fetch_listing_text(listing_url)

        vehicle = _enrich_from_ai_extract(vehicle, description, listing_url)
        vehicle = _fill_defaults(vehicle)

        desc_analysis = groq_service.analyze_description(
            description or vehicle.seller_description or "",
            vehicle.model_dump()
        )

        price_est = analysis_engine.calculate_fair_price(vehicle)
        ownership = analysis_engine.calculate_ownership_costs(vehicle, price_est)
        risks = analysis_engine.detect_risks(vehicle, price_est, desc_analysis, [])
        comparables = analysis_engine.find_comparable_vehicles(vehicle, price_est)
        deal = analysis_engine.calculate_deal_score(vehicle, price_est, risks, [])
        neg = analysis_engine.generate_negotiation_range(vehicle, price_est, risks, ownership)
        rec = analysis_engine.generate_recommendation(deal, risks, price_est)

        return {
            "vehicle": vehicle,
            "price_estimate": price_est,
            "ownership_costs": ownership,
            "deal_score": deal,
            "risks": risks,
            "comparables": comparables,
            "negotiation": neg,
            "recommendation": rec,
            "description_analysis": desc_analysis,
            "analysis_id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat()
        }

    except Exception as e:
        logger.exception(f"Listing analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Listing analysis failed: {str(e)}")


@router.post("/analyze/images")
async def analyze_images(
    files: List[UploadFile] = File(..., description="Vehicle images to analyze"),
    vehicle_json: Optional[str] = Form(None, description="Optional VehicleDetails as JSON string")
):
    try:
        vehicle = VehicleDetails()
        if vehicle_json:
            try:
                data = json.loads(vehicle_json)
                vehicle = VehicleDetails(**data)
            except Exception as pe:
                logger.warning(f"Parsing vehicle_json failed: {pe}. Using defaults.")

        images_b64 = []
        for f in files:
            content = await f.read()
            import base64
            b64 = base64.b64encode(content).decode("utf-8")
            mime = f.content_type or "image/jpeg"
            images_b64.append(f"data:{mime};base64,{b64}")

        if not images_b64:
            raise HTTPException(status_code=400, detail="No valid images provided")

        vehicle_dict = vehicle.model_dump()
        image_results_raw = gemini_service.analyze_multiple_images(images_b64, vehicle_dict)
        vehicle = _merge_identified_from_images(vehicle, image_results_raw)
        vehicle = _fill_defaults(vehicle)
        image_scores = [r.get("condition_score", 70) for r in image_results_raw]

        image_analyses = []
        for idx, img_r in enumerate(image_results_raw):
            try:
                obs = [{
                    "category": o.get("category", ""),
                    "observation": o.get("observation", ""),
                    "severity": str(o.get("severity", "medium")),
                    "requires_professional_inspection": o.get("requires_professional_inspection", False),
                    "confidence": float(img_r.get("ai_confidence", 0.7))
                } for o in img_r.get("observations", [])]
                dmg = [{
                    "type": d.get("type", ""),
                    "location": d.get("location", ""),
                    "severity": d.get("severity", ""),
                    "cost": d.get("repair_estimate_inr", 0)
                } for d in img_r.get("damage_details", [])]
                image_analyses.append(ImageAnalysis(
                    image_index=idx,
                    overall_condition=img_r.get("overall_condition", "Good"),
                    condition_score=img_r.get("condition_score", 70),
                    observations=obs,
                    damage_detected=img_r.get("damage_detected", False),
                    damage_details=dmg,
                    modifications_detected=img_r.get("modifications_detected", False),
                    modification_details=img_r.get("modification_details", []),
                    authenticity_notes=img_r.get("authenticity_notes", ""),
                    ai_confidence=img_r.get("ai_confidence", 0.7)
                ))
            except Exception as ie:
                logger.warning(f"Image analysis entry {idx} build failed: {ie}")

        price_est = analysis_engine.calculate_fair_price(vehicle)
        ownership = analysis_engine.calculate_ownership_costs(vehicle, price_est)
        risks = analysis_engine.detect_risks(vehicle, price_est, None, image_results_raw)
        comparables = analysis_engine.find_comparable_vehicles(vehicle, price_est)
        deal = analysis_engine.calculate_deal_score(vehicle, price_est, risks, image_scores)
        neg = analysis_engine.generate_negotiation_range(vehicle, price_est, risks, ownership)
        rec = analysis_engine.generate_recommendation(deal, risks, price_est)

        avg_condition = (sum(image_scores) / len(image_scores)) if image_scores else 70
        overall_verdict = f"Image analysis complete. Overall visual condition {avg_condition:.0f}/100. "
        if any(a.damage_detected for a in image_analyses):
            overall_verdict += "Damage detected in images - inspection recommended. "
        else:
            overall_verdict += "No significant damage visible in uploaded images. "

        return {
            "vehicle": vehicle,
            "image_analyses": image_analyses,
            "average_condition_score": avg_condition,
            "overall_verdict": overall_verdict,
            "price_estimate": price_est,
            "deal_score": deal,
            "risks": risks,
            "comparables": comparables,
            "ownership_costs": ownership,
            "negotiation": neg,
            "recommendation": rec,
            "image_count": len(images_b64),
            "analysis_id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat()
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Image analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {str(e)}")


@router.post("/analyze/screenshots")
async def analyze_screenshots(
    files: List[UploadFile] = File(..., description="Listing screenshots"),
    vehicle_json: Optional[str] = Form(None),
):
    try:
        vehicle = VehicleDetails()
        extra_desc = ""
        if vehicle_json:
            try:
                data = json.loads(vehicle_json)
                extra_desc = data.get("seller_description") or ""
                vehicle = VehicleDetails(**{k: v for k, v in data.items() if k in VehicleDetails.model_fields})
            except Exception as pe:
                logger.warning(f"Parsing vehicle_json failed: {pe}")

        images_b64 = []
        ocr_chunks = []
        for f in files:
            content = await f.read()
            import base64
            b64 = base64.b64encode(content).decode("utf-8")
            mime = f.content_type or "image/jpeg"
            data_uri = f"data:{mime};base64,{b64}"
            images_b64.append(data_uri)
            shot = gemini_service.analyze_listing_screenshot(data_uri)
            extracted = (shot or {}).get("vehicle_details_extracted") or {}
            ocr_text = (shot or {}).get("listing_text_ocr") or ""
            if ocr_text:
                ocr_chunks.append(ocr_text)
            current = vehicle.model_dump()
            for key, val in extracted.items():
                if val is not None and key in VehicleDetails.model_fields and (
                    current.get(key) is None or current.get(key) == ""
                ):
                    current[key] = val
            vehicle = VehicleDetails(**current)

        combined_desc = "\n".join([p for p in [extra_desc, *ocr_chunks] if p])
        vehicle = _enrich_from_ai_extract(vehicle, combined_desc, vehicle.listing_url)
        vehicle = _fill_defaults(vehicle)

        vehicle_dict = vehicle.model_dump()
        image_results_raw = gemini_service.analyze_multiple_images(images_b64, vehicle_dict)
        image_scores = [r.get("condition_score", 0) for r in image_results_raw]

        image_analyses = []
        for idx, img_r in enumerate(image_results_raw):
            obs = [{
                "category": o.get("category", ""),
                "observation": o.get("observation", ""),
                "severity": str(o.get("severity", "medium")),
                "requires_professional_inspection": o.get("requires_professional_inspection", False),
                "confidence": float(img_r.get("ai_confidence", 0.0)),
            } for o in img_r.get("observations", [])]
            dmg = [{
                "type": d.get("type", ""),
                "location": d.get("location", ""),
                "severity": d.get("severity", ""),
                "cost": d.get("repair_estimate_inr", 0),
            } for d in img_r.get("damage_details", [])]
            image_analyses.append(ImageAnalysis(
                image_index=idx,
                overall_condition=img_r.get("overall_condition", "Unknown"),
                condition_score=img_r.get("condition_score", 0),
                observations=obs,
                damage_detected=img_r.get("damage_detected", False),
                damage_details=dmg,
                modifications_detected=img_r.get("modifications_detected", False),
                modification_details=img_r.get("modification_details", []),
                authenticity_notes=img_r.get("authenticity_notes", ""),
                ai_confidence=img_r.get("ai_confidence", 0.0),
            ))

        desc_analysis = groq_service.analyze_description(combined_desc, vehicle_dict)
        price_est = analysis_engine.calculate_fair_price(vehicle)
        ownership = analysis_engine.calculate_ownership_costs(vehicle, price_est)
        risks = analysis_engine.detect_risks(vehicle, price_est, desc_analysis, image_results_raw)
        comparables = analysis_engine.find_comparable_vehicles(vehicle, price_est)
        deal = analysis_engine.calculate_deal_score(vehicle, price_est, risks, image_scores)
        neg = analysis_engine.generate_negotiation_range(vehicle, price_est, risks, ownership)
        rec = analysis_engine.generate_recommendation(deal, risks, price_est)
        avg_condition = (sum(image_scores) / len(image_scores)) if image_scores else 0

        return {
            "vehicle": vehicle,
            "image_analyses": image_analyses,
            "average_condition_score": avg_condition,
            "overall_verdict": f"Screenshot OCR + visual analysis complete. Condition {avg_condition:.0f}/100.",
            "price_estimate": price_est,
            "deal_score": deal,
            "risks": risks,
            "comparables": comparables,
            "ownership_costs": ownership,
            "negotiation": neg,
            "recommendation": rec,
            "description_analysis": desc_analysis,
            "image_count": len(images_b64),
            "analysis_id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat(),
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Screenshot analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Screenshot analysis failed: {str(e)}")


@router.post("/compare", response_model=ComparisonResult)
async def compare_vehicles(request: ComparisonRequest):
    try:
        if not request.vehicles or len(request.vehicles) < 2:
            raise HTTPException(status_code=400, detail="At least 2 vehicles required for comparison")

        items = []
        for idx, v in enumerate(request.vehicles):
            v_full = _fill_defaults(v)
            pe = analysis_engine.calculate_fair_price(v_full)
            oc = analysis_engine.calculate_ownership_costs(v_full, pe)
            risks = analysis_engine.detect_risks(v_full, pe)
            ds = analysis_engine.calculate_deal_score(v_full, pe, risks)
            items.append(ComparisonItem(
                vehicle=v_full,
                price_estimate=pe,
                deal_score=ds,
                ownership_costs=oc,
                risks=risks,
                rank=0
            ))

        items_sorted = sorted(items, key=lambda x: x.deal_score.overall, reverse=True)
        for r, it in enumerate(items_sorted):
            it.rank = r + 1

        winner = items_sorted[0]
        second = items_sorted[1] if len(items_sorted) > 1 else None
        winner_reason_parts = []
        score_gap = winner.deal_score.overall - (second.deal_score.overall if second else 0)
        winner_reason_parts.append(f"Top score {winner.deal_score.overall}/100 vs next best {second.deal_score.overall if second else 'N/A'}/100")
        if winner.price_estimate.price_difference_percent < 0:
            winner_reason_parts.append(f"Priced {abs(winner.price_estimate.price_difference_percent):.1f}% below market")
        if winner.deal_score.mileage_score > 80:
            winner_reason_parts.append("Mileage is excellent for age")
        if winner.deal_score.risk_score > 80:
            winner_reason_parts.append("Lowest risk profile")
        if winner.ownership_costs.total_true_cost < (second.ownership_costs.total_true_cost if second else float('inf')):
            winner_reason_parts.append("Lowest 3-yr total cost of ownership")

        winner_reason = "; ".join(winner_reason_parts)
        summary = (
            f"Compared {len(items)} vehicles. Best pick: "
            f"{winner.vehicle.brand} {winner.vehicle.model} ({winner.vehicle.manufacturing_year}) "
            f"at overall score {winner.deal_score.overall}/100. Key differentiator: "
            f"{' & '.join(winner_reason_parts[:2])}. "
            f"Detailed per-vehicle scores and financials available in respective entries."
        )

        return ComparisonResult(
            vehicles=items_sorted,
            recommendation_index=0,
            summary=summary,
            winner_reason=winner_reason
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Comparison failed: {e}")
        raise HTTPException(status_code=500, detail=f"Vehicle comparison failed: {str(e)}")


_saved_vehicles_store: Dict[str, Dict[str, Any]] = {}


@router.post("/save")
async def save_vehicle(saved: SavedVehicle):
    try:
        save_id = saved.id or f"save_{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()
        record = saved.model_dump()
        record["id"] = save_id
        record["saved_at"] = saved.saved_at or now
        _saved_vehicles_store[save_id] = record

        return {
            "status": "saved",
            "id": save_id,
            "saved_at": record["saved_at"],
            "vehicle_summary": {
                "brand": record.get("vehicle", {}).get("brand", ""),
                "model": record.get("vehicle", {}).get("model", ""),
                "year": record.get("vehicle", {}).get("manufacturing_year", ""),
                "asking_price": record.get("vehicle", {}).get("asking_price", 0)
            },
            "total_saved": len(_saved_vehicles_store)
        }
    except Exception as e:
        logger.exception(f"Save failed: {e}")
        raise HTTPException(status_code=500, detail=f"Save failed: {str(e)}")


@router.post("/negotiate")
async def generate_negotiation(
    vehicle_json: str = Form(...),
    custom_context: Optional[str] = Form(None)
):
    try:
        try:
            v_data = json.loads(vehicle_json)
            vehicle = VehicleDetails(**v_data)
        except Exception as pe:
            raise HTTPException(status_code=400, detail=f"Invalid vehicle_json: {pe}")

        vehicle = _fill_defaults(vehicle)

        pe = analysis_engine.calculate_fair_price(vehicle)
        oc = analysis_engine.calculate_ownership_costs(vehicle, pe)
        risks = analysis_engine.detect_risks(vehicle, pe)

        neg = analysis_engine.generate_negotiation_range(vehicle, pe, risks, oc)

        extra_neg = groq_service.generate_negotiation_message(
            asking_price=pe.asking_price,
            fair_price_mid=pe.fair_price_mid,
            vehicle_details=vehicle.model_dump(),
            risks=[r.model_dump() for r in risks],
            price_difference_percent=pe.price_difference_percent
        )

        if custom_context:
            neg.negotiation_message += f"\n\n[Additional Context: {custom_context}]"

        return {
            "vehicle": vehicle,
            "price_estimate": pe,
            "negotiation": neg,
            "ai_leverage": extra_neg,
            "script_template": {
                "greeting": f"Hi, I saw your {vehicle.brand} {vehicle.model} {vehicle.manufacturing_year} listing and I'm genuinely interested. I've been looking for exactly this spec for 2 weeks now.",
                "anchoring": f"I've checked Cars24, Spinny and OLX comparables, and the 2019 {vehicle.model} market is ₹{pe.fair_price_min:,.0f}-₹{pe.fair_price_max:,.0f} for this mileage.",
                "cost_anchoring": f"Also, I'll need to budget ~₹{oc.immediate_maintenance + oc.tyres + oc.battery + oc.upcoming_servicing:,.0f} day one for service + tyres + insurance.",
                "closing_leverage": "I have ready cash and can pay 50% advance today after inspection, with RC transfer done this week at the RTO - no loan delays.",
                "walk_away_anchor": f"Please share your best price - I also have a {vehicle.brand} {vehicle.model} test drive scheduled tomorrow at ₹{neg.target_price_min:,.0f} in {vehicle.location or 'the same city'}."
            },
            "negotiation_id": str(uuid.uuid4()),
            "generated_at": datetime.now().isoformat()
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Negotiation generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Negotiation generation failed: {str(e)}")


@router.get("/saved")
async def list_saved():
    return {
        "count": len(_saved_vehicles_store),
        "saved_vehicles": list(_saved_vehicles_store.values())
    }


@router.get("/sample")
async def get_sample_analysis():
    sample_vehicle = VehicleDetails(
        brand="Toyota",
        model="Innova Crysta",
        variant="2.4 VX 7 STR",
        manufacturing_year=2019,
        registration_year=2019,
        kilometers_driven=58000,
        fuel_type="Diesel",
        transmission="Manual",
        ownership="Second Owner",
        location="Bengaluru, Karnataka",
        asking_price=1625000,
        color="Pearl White",
        body_type="MUV",
        insurance_valid="Valid till Dec 2026",
        rto="KA-01",
        seller_description="Company-maintained Toyota Innova Crysta VX. All services done at Toyota BBT Bangalore. Non-accident, single hand driven by company executive. New Apollo tyres at 53,000 km. Battery replaced Oct 2024. Full service book available. Flooring, seat covers, Android stereo added. Reason for sale: upgrading to Fortuner. No dealers / brokers / agents. Slight negotiable only after test drive.",
        listing_url="https://olx.in/item/toyota-innova-crysta-vx-2019-diesel-58000km-id-1234567890"
    )
    request = AnalysisRequest(
        vehicle_details=sample_vehicle,
        images=[],
        description=sample_vehicle.seller_description,
        listing_url=sample_vehicle.listing_url
    )
    return await analyze_full_pipeline(request)


@router.post("/chat")
async def chat_with_ai(payload: dict):
    """Gemini-powered car assistant chatbot endpoint."""
    import os, requests as req
    try:
        user_message = payload.get("message", "").strip()
        history = payload.get("history", [])

        if not user_message:
            raise HTTPException(status_code=400, detail="Message is required")

        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if not gemini_key:
            raise HTTPException(status_code=503, detail="AI service not configured")

        system_prompt = """You are CarLens AI Assistant — an expert Indian used car advisor powered by Google Gemini.
Help users with: used car prices in India (INR ₹), fair market value, car features, variants, what to check before buying, negotiation tips, financing, insurance, ownership costs.
Focus on Indian brands: Maruti Suzuki, Hyundai, Tata, Mahindra, Kia, Toyota, Honda, etc.
Keep responses concise (under 150 words), friendly, and helpful. For full analysis suggest using the Analyze Car feature."""

        contents = []
        for h in history[-6:]:
            role = "user" if h.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})

        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 400, "temperature": 0.7},
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={gemini_key}"
        response = req.post(url, json=body, verify=False, timeout=30)
        data = response.json()

        if "error" in data:
            raise HTTPException(status_code=500, detail=data["error"].get("message", "Gemini error"))

        reply = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "Sorry, no response.")
        return {"reply": reply, "error": False}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception(f"Chat endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


# ── Vehicle Master DB Endpoints ───────────────────────────────────────────────

@router.get("/vehicles/makes")
async def get_makes():
    """Get all manufacturers from the vehicle master DB."""
    try:
        from app.database import get_all_manufacturers
        makes = get_all_manufacturers()
        return {"makes": makes, "count": len(makes)}
    except Exception as e:
        logger.exception(f"get_makes failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vehicles/models/{manufacturer_slug}")
async def get_models(manufacturer_slug: str):
    """Get all models for a manufacturer."""
    try:
        from app.database import get_models_by_manufacturer
        models = get_models_by_manufacturer(manufacturer_slug)
        return {"models": models, "count": len(models), "manufacturer": manufacturer_slug}
    except Exception as e:
        logger.exception(f"get_models failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vehicles/years/{manufacturer_slug}/{model_slug}")
async def get_years(manufacturer_slug: str, model_slug: str):
    """Get available years for a model."""
    try:
        from app.database import get_model_years
        years = get_model_years(model_slug, manufacturer_slug)
        return {"years": [y["model_year"] for y in years], "model": model_slug}
    except Exception as e:
        logger.exception(f"get_years failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vehicles/variants/{model_slug}/{year}")
async def get_variants(model_slug: str, year: int):
    """Get variants for a model year."""
    try:
        from app.database import get_variants
        variants = get_variants(model_slug, year)
        return {"variants": variants, "count": len(variants)}
    except Exception as e:
        logger.exception(f"get_variants failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Listings Endpoints ────────────────────────────────────────────────────────

@router.get("/listings/search")
async def search_listings(
    brand: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[int] = None,
    fuel: Optional[str] = None,
    transmission: Optional[str] = None,
    location: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    max_km: Optional[int] = None,
    feed_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    """Search used car listings from the listings database."""
    try:
        from app.database import get_listings, get_listing_count
        
        listings = get_listings(
            brand=brand, model=model, year=year,
            fuel=fuel, transmission=transmission, location=location,
            min_price=min_price, max_price=max_price, max_km=max_km,
            feed_type=feed_type,
            limit=limit, offset=offset,
        )
        total = get_listing_count(brand=brand, model=model, year=year)
        return {
            "listings": listings,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
            "filters_applied": {
                "brand": brand,
                "model": model,
                "year": year,
                "fuel": fuel,
                "transmission": transmission,
                "location": location,
                "feed_type": feed_type,
            }
        }
    except Exception as e:
        logger.exception(f"search_listings failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/listings/market-stats")
async def market_stats(
    brand: str,
    model: str,
    year: Optional[int] = None,
):
    """Get observed market price stats for a vehicle."""
    try:
        from app.database import get_market_stats
        stats = get_market_stats(brand=brand, model=model, year=year)
        return {
            "brand": brand,
            "model": model,
            "year": year,
            "stats": stats,
            "data_type": "observed_market_data",
            "note": "Based on observed listings — not a guaranteed price.",
            "last_computed": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.exception(f"market_stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── RSS Sync Endpoints ────────────────────────────────────────────────────────

@router.post("/rss/sync")
async def sync_rss(feed_type: str = "used_cars"):
    """Fetch RSS feed from specified type and store new items. Trigger periodically."""
    try:
        from app.services.rss_service import sync_rss_to_db
        result = sync_rss_to_db(feed_type)
        return result
    except Exception as e:
        logger.exception(f"RSS sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rss/sync/all")
async def sync_all_rss():
    """Sync all RSS feeds (used_cars, overall_both, new_cars)."""
    try:
        from app.services.rss_service import sync_all_rss_feeds
        result = sync_all_rss_feeds()
        return result
    except Exception as e:
        logger.exception(f"RSS sync all failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rss/process")
async def process_rss(limit: int = 10):
    """Run Groq extraction on unprocessed RSS items → listings DB."""
    try:
        from app.services.rss_service import process_unprocessed_items
        result = process_unprocessed_items(limit=limit)
        return result
    except Exception as e:
        logger.exception(f"RSS process failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Fix /api/save to persist to Neon DB ──────────────────────────────────────

@router.post("/save/analysis")
async def save_analysis_to_db(data: dict):
    """Persist an analysis result to Neon DB."""
    try:
        from app.database import save_analysis
        analysis_id = data.get("id") or data.get("analysis_id") or str(uuid.uuid4())
        save_analysis(analysis_id, data)
        return {"saved": True, "id": analysis_id}
    except Exception as e:
        logger.exception(f"save_analysis_to_db failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/saved/analyses")
async def get_saved_from_db(session: str = "default", limit: int = 50):
    """Get saved analyses from Neon DB."""
    try:
        from app.database import get_saved_analyses
        records = get_saved_analyses(session=session, limit=limit)
        return {"records": records, "count": len(records)}
    except Exception as e:
        logger.exception(f"get_saved_from_db failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/saved/analyses/{analysis_id}")
async def delete_saved_analysis(analysis_id: str):
    """Delete a saved analysis from Neon DB."""
    try:
        from app.database import delete_analysis
        delete_analysis(analysis_id)
        return {"deleted": True, "id": analysis_id}
    except Exception as e:
        logger.exception(f"delete_saved_analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
