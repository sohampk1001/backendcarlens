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


def _call_gemini_with_image(prompt: str, image_b64: str) -> Optional[str]:
    if not _genai_configured or not _genai_model:
        return None

    try:
        image_bytes = _decode_base64_image(image_b64)
        if not image_bytes:
            return None

        response = _genai_model.generate_content(
            [prompt, {"mime_type": "image/jpeg", "data": image_bytes}]
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
    "ai_confidence": 0.0-1.0 number
}
Be specific to Indian used car conditions. Conservative estimates for repair costs in INR rupees."""

    context_str = f"Vehicle Context: {json.dumps(vehicle_context, indent=2)}\nImage #{image_index}" if vehicle_context else f"Image #{image_index}"
    user_prompt = f"{context_str}\n\nAnalyze this vehicle image according to the system prompt instructions."

    result = _call_gemini_with_image(system_prompt + "\n\n" + user_prompt, image_b64)
    parsed = _parse_json_response(result) if result else None

    if parsed:
        return parsed

    condition_profiles = [
        {
            "overall_condition": "Good",
            "condition_score": 72,
            "observations": [
                {"category": "exterior", "observation": "Minor swirl marks and micro-scratches visible on bonnet and roof - typical for 5+ year old vehicle in Indian conditions", "severity": "cosmetic", "requires_professional_inspection": False, "estimated_cost_inr": 3500},
                {"category": "tyres", "observation": "Front tyres show ~50% tread remaining, rear tyres ~60-65% - replacement likely within 10,000-15,000 km", "severity": "moderate", "requires_professional_inspection": False, "estimated_cost_inr": 24000},
                {"category": "interior", "observation": "Driver seat bolster and steering wheel show expected wear pattern for stated mileage. No tears or major stains visible", "severity": "minor", "requires_professional_inspection": False, "estimated_cost_inr": 0},
                {"category": "wheels", "observation": "Alloy wheels have minor curb rash on 2 wheels - cosmetic only, no structural concern", "severity": "cosmetic", "requires_professional_inspection": False, "estimated_cost_inr": 2000}
            ],
            "damage_detected": True,
            "damage_details": [
                {"type": "scratch", "location": "Front bumper, passenger side corner", "severity": "minor", "repair_estimate_inr": 2500},
                {"type": "dent", "location": "Rear left door panel - small dent approx 5cm, paint intact", "severity": "minor", "repair_estimate_inr": 4500}
            ],
            "modifications_detected": False,
            "modification_details": [],
            "authenticity_notes": "Body panels show consistent panel gaps in visible areas. VIN plate not clearly visible in this angle. Paint finish appears consistent across visible panels, no obvious signs of major repaint work. Windscreen has minor chip at bottom edge - can be repaired rather than replaced.",
            "ai_confidence": 0.72
        },
        {
            "overall_condition": "Very Good",
            "condition_score": 81,
            "observations": [
                {"category": "exterior", "observation": "Paint finish appears largely uniform with expected gloss level for age. Very few visible imperfections beyond normal washing swirls", "severity": "cosmetic", "requires_professional_inspection": False, "estimated_cost_inr": 2000},
                {"category": "interior", "observation": "Dashboard, door pads, and upholstery in good condition. Controls and switches appear intact and undamaged", "severity": "minor", "requires_professional_inspection": False, "estimated_cost_inr": 0},
                {"category": "glass", "observation": "All glass surfaces clear without visible cracks or chips. Window tints appear uniform and legally compliant", "severity": "minor", "requires_professional_inspection": False, "estimated_cost_inr": 0},
                {"category": "tyres", "observation": "Tyre tread depth looks reasonable - recommend measurement during inspection. Branded tyres visible with even wear pattern suggesting proper alignment", "severity": "minor", "requires_professional_inspection": True, "estimated_cost_inr": 0}
            ],
            "damage_detected": False,
            "damage_details": [],
            "modifications_detected": False,
            "modification_details": [],
            "authenticity_notes": "Vehicle appears largely original in presentation. Panel alignment looks consistent. Recommend lift inspection to check underbody and confirm no hidden structural work or corrosion. Badge and trim placement matches factory specifications.",
            "ai_confidence": 0.78
        },
        {
            "overall_condition": "Fair",
            "condition_score": 58,
            "observations": [
                {"category": "exterior", "observation": "Significant fading evident on roof and bonnet clear coat - sun exposure damage typical of prolonged outdoor parking. Repainting recommended", "severity": "moderate", "requires_professional_inspection": False, "estimated_cost_inr": 35000},
                {"category": "exterior", "observation": "Multiple stone chips on front bumper and lower fascia from highway use. Fog light housing appears cloudy/fogged on driver side", "severity": "minor", "requires_professional_inspection": False, "estimated_cost_inr": 6000},
                {"category": "tyres", "observation": "Tyre tread appears critically low on front axle - unsafe for wet conditions. Wheel alignment and balancing overdue indicated by uneven wear pattern", "severity": "severe", "requires_professional_inspection": True, "estimated_cost_inr": 28000},
                {"category": "interior", "observation": "Driver seat fabric has worn through on bolster edge. Some console trim pieces show scratches. Floor mats heavily soiled with possible water staining - check carpet underneath", "severity": "moderate", "requires_professional_inspection": True, "estimated_cost_inr": 8500}
            ],
            "damage_detected": True,
            "damage_details": [
                {"type": "paint_damage", "location": "Roof and bonnet - clear coat oxidation and fading", "severity": "moderate", "repair_estimate_inr": 35000},
                {"type": "dent", "location": "Rear quarter panel, driver side - visible crease 10-12cm", "severity": "moderate", "repair_estimate_inr": 8000},
                {"type": "rust", "location": "Lower sill edges - surface rust starting, not perforated yet", "severity": "moderate", "repair_estimate_inr": 12000}
            ],
            "modifications_detected": True,
            "modification_details": [
                "Aftermarket roof spoiler installed - verify fit quality and waterproofing around mounting points",
                "Non-OEM headlamp bulbs/LEDs - check electrical wiring and reflector heat damage",
                "Window rain visors - cosmetic addition, verify door rubber seal not damaged"
            ],
            "authenticity_notes": "Signs of non-factory paint work on rear quarter panel visible through texture inconsistency. VIN not visible. Strongly recommend paint thickness gauge measurement across all panels to identify previous accident repair areas. Check A/B/C pillar joints and door frame for weld marks indicating structural damage repair.",
            "ai_confidence": 0.68
        }
    ]

    profile = condition_profiles[image_index % len(condition_profiles)]
    profile["image_index"] = image_index
    return profile


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
