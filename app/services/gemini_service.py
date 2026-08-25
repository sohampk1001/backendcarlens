import os
import json
import base64
import logging
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-flash-latest"

_genai_configured = False
_genai_model = None

try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        safety_settings = [
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
        ]
        _genai_model = genai.GenerativeModel(GEMINI_MODEL, safety_settings=safety_settings)
        _genai_configured = True
        logger.info("Gemini client initialized successfully")
    else:
        logger.warning("GEMINI_API_KEY not found, using mock image analysis responses")
except Exception as e:
    logger.warning(f"Failed to initialize Gemini client: {e}. Using mock responses.")
    _genai_configured = False
    _genai_model = None


def _decode_base64_image(base64_str: str) -> Optional[bytes]:
    try:
        if base64_str.startswith("data:image"):
            base64_str = base64_str.split(",", 1)[1]
        return base64.b64decode(base64_str)
    except Exception as e:
        logger.error(f"Failed to decode base64 image: {e}")
        return None


def _mime_from_data_uri(image_b64: str) -> str:
    if image_b64.startswith("data:") and ";base64," in image_b64:
        header = image_b64.split(";base64,", 1)[0]
        mime = header.replace("data:", "").strip() or "image/jpeg"
        if mime in ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"):
            return "image/jpeg" if mime == "image/jpg" else mime
    return "image/jpeg"


def _call_gemini_with_image(prompt: str, image_b64: str) -> Optional[str]:
    if not _genai_configured or not _genai_model:
        return None

    try:
        image_bytes = _decode_base64_image(image_b64)
        if not image_bytes:
            return None

        mime = _mime_from_data_uri(image_b64)
        response = _genai_model.generate_content(
            [prompt, {"mime_type": mime, "data": image_bytes}]
        )
        if response and response.text:
            return response.text
        return None
    except Exception as e:
        logger.error(f"Gemini image analysis API call failed: {e}")
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
        logger.warning(f"Failed to parse JSON from Gemini response: {e}")
        return None


def analyze_vehicle_image(image_b64: str, vehicle_context: Optional[Dict[str, Any]] = None, image_index: int = 0) -> Dict[str, Any]:
    system_prompt = """You are an expert automotive visual inspector. Analyze this vehicle image thoroughly. Return ONLY valid JSON with:
{
    "overall_condition": "Excellent/Very Good/Good/Fair/Poor",
    "condition_score": 0-100 integer,
    "observations": [
        {"category": "exterior/interior/engine/tyres/wheels/glass/electricals", "observation": "specific detail", "severity": "cosmetic/minor/moderate/severe", "requires_professional_inspection": true/false, "estimated_cost_inr": number}
    ],
    "damage_detected": boolean,
    "damage_details": [
        {"type": "dent/scratch/paint_damage/rust/crack/wear/tear", "location": "specific area", "severity": "minor/moderate/severe", "repair_estimate_inr": number}
    ],
    "modifications_detected": boolean,
    "modification_details": ["list of aftermarket changes detected"],
    "authenticity_notes": "Any mismatch with typical vehicle trim, VIN plate visible, signs of repaint, title/branding inconsistencies",
    "ai_confidence": 0.0-1.0 number,
    "identified_vehicle": {
        "brand": "make if visible, else empty string",
        "model": "model if visible, else empty string",
        "variant": "variant if visible, else empty string",
        "manufacturing_year": "integer year if badge/plate/listing text is readable, else null",
        "color": "body color if visible, else empty string",
        "body_type": "Hatchback/Sedan/SUV/MUV/Coupe if identifiable, else empty string"
    }
}
Identify the car make/model from badges, grille, lamps and body shape when possible. Be specific to Indian used car conditions. Conservative estimates for repair costs in INR rupees."""

    context_str = f"Vehicle Context: {json.dumps(vehicle_context, indent=2)}\nImage #{image_index}" if vehicle_context else f"Image #{image_index}"
    user_prompt = f"{context_str}\n\nAnalyze this vehicle image according to the system prompt instructions."

    result = _call_gemini_with_image(system_prompt + "\n\n" + user_prompt, image_b64)
    parsed = _parse_json_response(result) if result else None

    if parsed:
        parsed["image_index"] = image_index
        parsed["ai_source"] = "gemini"
        return parsed

    reason = "Gemini did not return a usable visual analysis for this image."
    if not _genai_configured:
        reason = "GEMINI_API_KEY is not configured on the server."
    return {
        "image_index": image_index,
        "overall_condition": "Unknown",
        "condition_score": 0,
        "observations": [{
            "category": "system",
            "observation": reason + " Upload a clear car photo (exterior/interior) and try again.",
            "severity": "minor",
            "requires_professional_inspection": True,
            "estimated_cost_inr": 0,
        }],
        "damage_detected": False,
        "damage_details": [],
        "modifications_detected": False,
        "modification_details": [],
        "authenticity_notes": reason,
        "ai_confidence": 0.0,
        "ai_source": "unavailable",
    }


def analyze_listing_screenshot(image_b64: str) -> Dict[str, Any]:
    system_prompt = """You are an expert OCR and listing screenshot extractor for Indian used car portals (OLX, Cars24, Spinny, CarDekho, Quikr etc). Analyze this listing screenshot and extract ALL information. Return ONLY valid JSON with:
{
    "vehicle_details_extracted": {
        "brand": string, "model": string, "variant": string,
        "manufacturing_year": integer, "registration_year": integer,
        "kilometers_driven": integer,
        "fuel_type": "Petrol/Diesel/CNG/Electric/Hybrid",
        "transmission": "Manual/Automatic",
        "ownership": "First Owner/Second Owner/Third Owner/Fourth+ Owner",
        "location": "City, State",
        "asking_price": number_in_inr_rupees,
        "color": string,
        "body_type": string
    },
    "seller_info": {
        "seller_type": "Individual/Dealer/Certified",
        "seller_name": string,
        "contact_visible": boolean,
        "listing_age_days": integer_or_null,
        "platform": "OLX/Cars24/Spinny/CarDekho/Quikr/Other"
    },
    "listing_text_ocr": "FULL extracted text from the screenshot",
    "confidence_scores": {
        "price_extraction": 0.0-1.0,
        "vehicle_specs": 0.0-1.0,
        "seller_info": 0.0-1.0
    },
    "additional_notes": "Anything unusual: price drop indication, urgency tags, featured listing, etc."
}"""

    result = _call_gemini_with_image(system_prompt, image_b64)
    parsed = _parse_json_response(result) if result else None

    if parsed:
        return parsed

    return {
        "vehicle_details_extracted": {
            "brand": None,
            "model": None,
            "variant": None,
            "manufacturing_year": None,
            "registration_year": None,
            "kilometers_driven": None,
            "fuel_type": None,
            "transmission": None,
            "ownership": None,
            "location": None,
            "asking_price": None,
            "color": None,
            "body_type": None
        },
        "seller_info": {
            "seller_type": "Unknown",
            "seller_name": None,
            "contact_visible": False,
            "listing_age_days": None,
            "platform": "Unknown"
        },
        "listing_text_ocr": "[OCR unavailable - mock fallback mode]",
        "confidence_scores": {
            "price_extraction": 0.0,
            "vehicle_specs": 0.0,
            "seller_info": 0.0
        },
        "additional_notes": "Screenshot analysis unavailable in offline mode. Please provide manual vehicle details for analysis."
    }


def analyze_multiple_images(images_b64: List[str], vehicle_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    results = []
    for idx, img_b64 in enumerate(images_b64):
        try:
            analysis = analyze_vehicle_image(img_b64, vehicle_context, image_index=idx)
            results.append(analysis)
        except Exception as e:
            logger.error(f"Failed to analyze image {idx}: {e}")
            results.append({
                "image_index": idx,
                "overall_condition": "Unknown",
                "condition_score": 50,
                "observations": [],
                "damage_detected": False,
                "damage_details": [],
                "modifications_detected": False,
                "modification_details": [],
                "authenticity_notes": f"Image analysis failed: {str(e)}",
                "ai_confidence": 0.0
            })
    return results
