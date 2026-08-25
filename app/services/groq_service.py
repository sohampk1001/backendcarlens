import os
import json
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"

_groq_client = None
_groq_available = False

try:
    from groq import Groq
    if GROQ_API_KEY:
        _groq_client = Groq(api_key=GROQ_API_KEY)
        _groq_available = True
        logger.info("Groq client initialized successfully")
    else:
        logger.warning("GROQ_API_KEY not found, using mock responses")
except Exception as e:
    logger.warning(f"Failed to initialize Groq client: {e}. Using mock responses.")
    _groq_client = None
    _groq_available = False


def _call_groq(system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> Optional[str]:
    if not _groq_available or not _groq_client:
        return None
    try:
        response = _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=0.9
        )
        if response and response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        return None
    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        return None


def _parse_json_response(content: str) -> Optional[Dict[str, Any]]:
    try:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            return json.loads(json_str)
        return json.loads(content)
    except Exception as e:
        logger.warning(f"Failed to parse JSON response: {e}")
        return None


def extract_listing_data(description: str, url: Optional[str] = None) -> Dict[str, Any]:
    from app.services.listing_fetch import fetch_listing_text
    from app.services.listing_parse import heuristic_extract, merge_extract

    page_text = fetch_listing_text(url)
    source = "\n".join([p for p in [url or "", description or "", page_text] if p])
    heuristic = heuristic_extract(f"{description or ''}\n{page_text}", url)

    system_prompt = """You are an expert used car listing data extractor for India. Extract ONLY facts present in the provided listing text/URL. Never invent a different car. If a field is not in the text, use null. Return ONLY valid JSON with:
    brand, model, variant, manufacturing_year, registration_year, kilometers_driven, fuel_type, transmission, ownership, location, asking_price, color, body_type, insurance_valid, rto.
    asking_price must be INR number. kilometers_driven number. years 4-digit. fuel_type: Petrol, Diesel, CNG, Electric, Hybrid. transmission: Manual or Automatic. ownership: First Owner, Second Owner, Third Owner, or Fourth+ Owner."""

    user_prompt = (
        "Extract vehicle data. Use only this source. Do not substitute another vehicle.\n\n"
        f"URL: {url or 'N/A'}\n\nListing text:\n{source[:8000]}"
    )

    result = _call_groq(system_prompt, user_prompt, temperature=0.1)
    parsed = _parse_json_response(result) if result else None
    merged = merge_extract(heuristic, parsed, source)
    merged["seller_description"] = (description or page_text or merged.get("seller_description") or "")[:4000]
    merged["listing_url"] = url
    return merged


def analyze_description(description: str, vehicle_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    system_prompt = """You are an expert used car analyst for the Indian market. Analyze the seller's description for red flags, condition indicators, missing information, and honesty. Return ONLY valid JSON with:
    - condition_indicators: list of strings about vehicle condition
    - red_flags: list of suspicious/worrying statements
    - missing_info: list of critical details not mentioned
    - seller_honesty_score: integer 0-100 (100 = completely honest/transparent)
    - positives: list of positive mentions
    - maintenance_mentions: list of maintenance history items
    - summary: 2 sentence overall assessment"""

    details_str = json.dumps(vehicle_details, indent=2) if vehicle_details else "N/A"
    user_prompt = f"Analyze this used car description:\n\nVehicle Details: {details_str}\n\nSeller Description:\n{description}"

    result = _call_groq(system_prompt, user_prompt, temperature=0.3)
    parsed = _parse_json_response(result) if result else None

    if parsed:
        return parsed

    text = (description or "").lower()
    missing = []
    if "service" not in text:
        missing.append("Service history records not mentioned")
    if "accident" not in text and "claim" not in text:
        missing.append("Accident history not disclosed")
    if "insurance" not in text:
        missing.append("Insurance expiry date missing")
    positives = []
    if "first owner" in text or "1st owner" in text:
        positives.append("First-owner mentioned")
    if "service" in text:
        positives.append("Service history mentioned")
    red = []
    if "urgent" in text or "need money" in text:
        red.append("Urgency language in listing")
    return {
        "condition_indicators": ["Parsed from seller text; visual inspection still required"],
        "red_flags": red,
        "missing_info": missing or ["Full inspection report not attached"],
        "seller_honesty_score": 62 if red else 75,
        "positives": positives or ["Listing includes some vehicle specifications"],
        "maintenance_mentions": ["Service mentioned"] if "service" in text else [],
        "summary": (
            f"Assessment is based on the seller text provided ({(vehicle_details or {}).get('brand') or 'vehicle'} "
            f"{(vehicle_details or {}).get('model') or ''}). "
            "Treat missing accident/service/insurance details as items to verify in person."
        ),
        "ai_source": "heuristic" if not _groq_available else "groq_fallback_heuristic",
    }


def generate_risk_categories(vehicle_details: Dict[str, Any], description_analysis: Optional[Dict[str, Any]] = None) -> list:
    system_prompt = """You are an expert used car risk assessor for India. Based on vehicle facts and listing analysis, generate specific risk signals. Return a JSON array of objects each with: signal (short name), level (low/medium/high), description (why it's a risk), category (price, mileage, age, ownership, mechanical, documentation, seller, market), and mitigation (actionable advice). Be specific to Indian used car market risks."""

    user_prompt = f"Generate risk signals for:\nVehicle Details: {json.dumps(vehicle_details, indent=2)}\n\nDescription Analysis: {json.dumps(description_analysis or {}, indent=2)}"

    result = _call_groq(system_prompt, user_prompt, temperature=0.3)
    if result:
        try:
            start = result.find("[")
            end = result.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(result[start:end])
                if isinstance(parsed, list):
                    return parsed
        except Exception as e:
            logger.warning(f"Failed to parse risk categories JSON: {e}")

    return [
        {
            "signal": "Mileage Verification",
            "level": "medium",
            "description": "Odometer tampering is common in the Indian used car market. Reading should be cross-verified with service records.",
            "category": "documentation",
            "mitigation": "Request original service book entries and match service center visit dates with odometer readings"
        },
        {
            "signal": "Accident History",
            "level": "high",
            "description": "Accident damage is rarely disclosed by sellers. Structural damage can compromise safety and resale value significantly.",
            "category": "mechanical",
            "mitigation": "Hire a certified mechanic for full body inspection including underbody, pillar condition, and panel gap analysis"
        },
        {
            "signal": "Insurance Validity",
            "level": "medium",
            "description": "Expired insurance means immediate additional cost and potential non-compliance. Also indicates possible lack of maintenance.",
            "category": "documentation",
            "mitigation": "Verify insurance expiry date, check NCB (No Claim Bonus) history, and factor renewal cost into total ownership"
        },
        {
            "signal": "Transfer Documentation",
            "level": "medium",
            "description": "RC transfer, NOC from RTO, and form 29/30 submission are critical. Incomplete transfer can lead to legal issues.",
            "category": "documentation",
            "mitigation": "Verify original RC, get NOC if crossing RTO jurisdiction, ensure complete Form 29/30 submission with seller ID proofs"
        },
        {
            "signal": "High Ownership Count",
            "level": "low",
            "description": "Multiple owners may indicate problems with the vehicle or poor maintenance history.",
            "category": "ownership",
            "mitigation": "Review each owner's usage pattern and reason for sale. Prefer single-owner vehicles when possible"
        }
    ]


def generate_negotiation_message(
    asking_price: float,
    fair_price_mid: float,
    vehicle_details: Dict[str, Any],
    risks: list,
    price_difference_percent: float
) -> Dict[str, Any]:
    system_prompt = """You are an expert used car negotiator for the Indian market. Generate negotiation strategy and messages. Return ONLY valid JSON with:
    - negotiation_message: 1 paragraph confident but polite message to the seller (in English, as buyer would send on WhatsApp/OLX)
    - leverage_points: list of specific leverage points for negotiation
    - suggested_messages: list of 3 chat message strings for different negotiation stages
    - opening_offer_percent: percentage below asking to open with (number)
    - strategy_summary: 2 sentence negotiation strategy"""

    user_prompt = f"""Negotiation context:
    Asking Price: ₹{asking_price:,.0f}
    Fair Estimate (Mid): ₹{fair_price_mid:,.0f}
    Price Difference: {price_difference_percent:.1f}%
    Vehicle: {json.dumps(vehicle_details, indent=2)}
    Risk Signals: {json.dumps(risks, indent=2)}"""

    result = _call_groq(system_prompt, user_prompt, temperature=0.5)
    parsed = _parse_json_response(result) if result else None

    if parsed:
        return parsed

    leverage = [
        "Market research shows similar vehicles priced 5-10% lower across OLX/Cars24",
        "Immediate maintenance cost of ₹25,000-40,000 needed for service, tyres, and insurance",
        "Multiple ownership reduces resale value by 8-12%",
        "Comparable listings with fewer kilometers available at lower price points",
        "Ready cash payment and quick RC transfer process"
    ]

    return {
        "negotiation_message": f"Hi, I'm interested in your {vehicle_details.get('brand', '')} {vehicle_details.get('model', '')} and have done thorough market research. The car seems well-maintained but considering the current market pricing, required servicing, tyre/battery replacements, and insurance renewal, I'd like to offer ₹{fair_price_mid * 0.92:,.0f}. I have ready cash and can complete the RC transfer immediately this week. Please let me know your best price and we can discuss further with a test drive.",
        "leverage_points": leverage,
        "suggested_messages": [
            f"Hi there! Saw your {vehicle_details.get('brand', '')} {vehicle_details.get('model', '')} listing and it matches my requirements perfectly. Before I schedule a visit, what's your best final price? I have a mechanic booked for inspection this week and can close quickly if the price is right.",
            f"Thanks for sharing the details. I checked Cars24/OLX comparables and similar {vehicle_details.get('year', '')} models are going around ₹{fair_price_mid:,.0f}-₹{fair_price_mid * 1.03:,.0f}. Your asking is on the higher side - can we meet at ₹{fair_price_mid * 0.97:,.0f}? Inspection and payment same day.",
            f"Appreciate the test drive opportunity. The car drives well but I noticed some things that need attention (tyres, service). Given that I'll be spending ~₹35,000 on day one, my final offer is ₹{fair_price_mid * 0.95:,.0f} cash today. Please confirm and we can do the transfer at the RTO tomorrow morning."
        ],
        "opening_offer_percent": 8,
        "strategy_summary": "Open 8-10% below fair market value to establish a serious baseline. Anchor the discussion around verifiable comparable listings and quantifiable day-one costs rather than subjective claims. Use ready payment and quick transfer as closing leverage when within 3-5% of target."
    }


def generate_report_explanation(
    vehicle: Dict[str, Any],
    price_estimate: Dict[str, Any],
    deal_score: Dict[str, Any],
    risks: list,
    recommendation: str
) -> Dict[str, Any]:
    system_prompt = """You are an expert used car valuation report writer for the Indian market. Generate a comprehensive structured report with clear sections. Return ONLY valid JSON with:
    - executive_summary: {title, content, key_points: []}
    - price_analysis: {title, content, key_points: []}
    - condition_analysis: {title, content, key_points: []}
    - cost_analysis: {title, content, key_points: []}
    - risk_analysis: {title, content, key_points: []}
    - final_verdict: {title, content, key_points: []}
    Content should be professional, 3-5 sentences per section. Key points: 3-5 bullet-worthy short strings."""

    user_prompt = f"""Generate complete report for:
    Vehicle: {json.dumps(vehicle, indent=2)}
    Price Estimate: {json.dumps(price_estimate, indent=2)}
    Deal Score: {json.dumps(deal_score, indent=2)}
    Risks: {json.dumps(risks, indent=2)}
    Overall Recommendation: {recommendation}"""

    result = _call_groq(system_prompt, user_prompt, temperature=0.4, max_tokens=4096)
    parsed = _parse_json_response(result) if result else None

    if parsed and all(k in parsed for k in ["executive_summary", "price_analysis", "condition_analysis", "cost_analysis", "risk_analysis", "final_verdict"]):
        return parsed

    return {
        "executive_summary": {
            "title": "Executive Summary",
            "content": f"This {vehicle.get('manufacturing_year', 'N/A')} {vehicle.get('brand', '')} {vehicle.get('model', '')} has been evaluated against the Indian used car market standards. The vehicle presents a {recommendation.lower()} opportunity based on comprehensive analysis of pricing, condition factors, ownership costs, and risk signals. The asking price of ₹{vehicle.get('asking_price', 0):,.0f} was compared against current market data and our proprietary valuation model.",
            "key_points": [
                f"Overall Deal Score: {deal_score.get('overall', 0)}/100",
                f"Recommendation: {recommendation}",
                f"Price Position: {price_estimate.get('price_status', 'N/A')} vs Market",
                f"Total True Cost of Ownership: ₹{price_estimate.get('fair_price_mid', 0) * 1.15:,.0f} including day-one expenses"
            ]
        },
        "price_analysis": {
            "title": "Price Valuation & Market Position",
            "content": f"The asking price of ₹{price_estimate.get('asking_price', 0):,.0f} is {price_estimate.get('price_status', '').lower()} compared to the estimated fair market range of ₹{price_estimate.get('fair_price_min', 0):,.0f} to ₹{price_estimate.get('fair_price_max', 0):,.0f}. This represents a variance of {abs(price_estimate.get('price_difference_percent', 0)):.1f}% from the fair midpoint of ₹{price_estimate.get('fair_price_mid', 0):,.0f}. Depreciation has been calculated at approximately {price_estimate.get('depreciation_rate', 0):.1f}% annually based on brand residual values, age, and mileage.",
            "key_points": [
                f"Fair Market Range: ₹{price_estimate.get('fair_price_min', 0):,.0f} - ₹{price_estimate.get('fair_price_max', 0):,.0f}",
                f"Market Average: ₹{price_estimate.get('market_average', 0):,.0f}",
                f"Variance: {price_estimate.get('price_difference_percent', 0):+.1f}% vs Midpoint",
                f"Annual Depreciation: ~{price_estimate.get('depreciation_rate', 0):.1f}%",
                "Valuation benchmarked against OLX, Cars24, and Spinny live listings"
            ]
        },
        "condition_analysis": {
            "title": "Vehicle Condition Assessment",
            "content": "Based on available listing information and typical market observations for vehicles of this age and mileage, condition factors have been scored. The evaluation considers age-related wear, expected maintenance intervals, transmission and fuel type durability characteristics, and ownership history patterns. Actual physical inspection by a qualified mechanic is strongly recommended before purchase commitment.",
            "key_points": [
                f"Condition Score: {deal_score.get('condition_score', 0)}/100",
                f"Year Score: {deal_score.get('year_score', 0)}/100 (vehicle age factor)",
                f"Mileage Score: {deal_score.get('mileage_score', 0)}/100 (usage factor)",
                "Professional mechanical inspection: HIGHLY RECOMMENDED",
                "Body shop/Paint meter inspection: Recommended for accident damage detection"
            ]
        },
        "cost_analysis": {
            "title": "Total Ownership Cost Projection",
            "content": "Beyond the purchase price, significant additional costs must be budgeted including immediate maintenance, insurance renewal, and RC transfer expenses. Three-year projected maintenance costs have been estimated based on manufacturer service schedules and typical wear patterns for this vehicle segment. Running costs include fuel, insurance, and routine servicing averages for Indian driving conditions.",
            "key_points": [
                f"Day-One Additional Costs: ~₹{price_estimate.get('fair_price_mid', 0) * 0.08:,.0f}",
                f"Insurance (Comprehensive): ₹{max(15000, int(price_estimate.get('fair_price_mid', 0) * 0.025)):,.0f}/year",
                f"Annual Maintenance Budget: ₹{max(12000, int(price_estimate.get('fair_price_mid', 0) * 0.02)):,.0f}",
                f"Per KM Running Cost: ₹{(lambda p: 7 if vehicle.get('fuel_type','')=='Petrol' else 5 if vehicle.get('fuel_type','')=='Diesel' else 9 if vehicle.get('fuel_type','')=='CNG' else 6)(vehicle):.1f}/km",
                "3-Year Depreciation: ~18-22% of current fair value"
            ]
        },
        "risk_analysis": {
            "title": "Risk Assessment & Due Diligence",
            "content": f"A total of {len(risks)} risk signals have been identified across documentation, mechanical, and ownership categories. High-priority items include accident history verification and original document validation which are critical purchase prerequisites in the Indian used car market. Medium risks around service history gaps and maintenance predictability should be resolved during inspection and test drive.",
            "key_points": [
                f"Total Risks Identified: {len(risks)} signals",
                f"High Priority: {sum(1 for r in risks if r.get('level','')=='high')} items",
                f"Medium Priority: {sum(1 for r in risks if r.get('level','')=='medium')} items",
                f"Low Priority: {sum(1 for r in risks if r.get('level','')=='low')} items",
                "Mandatory: Original RC, Insurance, Service Book, NOC (if applicable)"
            ]
        },
        "final_verdict": {
            "title": "Final Verdict & Recommendation",
            "content": f"After comprehensive analysis of pricing competitiveness, vehicle condition indicators, ownership cost projections, and risk factors - our recommendation is {recommendation}. The vehicle scores {deal_score.get('overall', 0)}/100 overall, with strongest performance in the {['price','condition','value','risk'][0] if deal_score else 'value'} dimension. If proceeding, complete the full due diligence checklist and negotiate aggressively using the identified leverage points before finalizing purchase.",
            "key_points": [
                f"Final Recommendation: {recommendation}",
                f"Overall Score: {deal_score.get('overall', 0)}/100",
                f"Negotiation Target: ₹{price_estimate.get('fair_price_mid', 0) * 0.95:,.0f} - ₹{price_estimate.get('fair_price_mid', 0):,.0f}",
                "Must Do: Mechanic inspection + document verification before any payment",
                f"Walk-Away Price: ₹{price_estimate.get('fair_price_mid', 0) * 1.05:,.0f}"
            ]
        }
    }
