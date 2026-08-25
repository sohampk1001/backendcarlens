import re
from typing import Any, Dict, Optional

INDIAN_CAR_DATA = {
    "Maruti Suzuki": ["Alto K10", "S-Presso", "Celerio", "WagonR", "Swift", "Baleno", "Ignis", "Dzire", "Ciaz", "Ertiga", "XL6", "Brezza", "Grand Vitara", "Fronx", "Jimny", "Invicto", "Alto", "Wagon R"],
    "Hyundai": ["Grand i10 Nios", "i10", "i20", "Aura", "Verna", "Exter", "Venue", "Creta", "Alcazar", "Tucson", "Ioniq 5", "Ioniq 6", "Kona Electric"],
    "Tata": ["Tiago EV", "Tiago", "Tigor EV", "Tigor", "Altroz", "Punch EV", "Punch", "Nexon EV", "Nexon", "Harrier", "Safari", "Curvv EV", "Curvv"],
    "Mahindra": ["Bolero Neo", "Scorpio Classic", "Scorpio-N", "Scorpio", "XUV300", "XUV400", "XUV700", "Thar Roxx", "Thar", "Bolero", "XUV 700"],
    "Kia": ["Sonet", "Seltos", "Carens", "EV6", "Carnival", "EV9"],
    "Toyota": ["Urban Cruiser Hyryder", "Innova Crysta", "Innova HyCross", "Innova", "Fortuner", "Glanza", "Hilux", "Camry", "Rumion"],
    "Honda": ["City e:HEV", "Amaze", "City", "Elevate", "Jazz"],
    "Renault": ["Kwid", "Triber", "Kiger", "Duster"],
    "Volkswagen": ["Polo", "Vento", "Taigun", "Virtus"],
    "Skoda": ["Rapid", "Slavia", "Kushaq", "Kodiaq", "Octavia", "Superb"],
    "MG": ["Hector Plus", "Hector", "Astor", "Gloster", "Comet EV", "ZS EV"],
    "Jeep": ["Compass", "Meridian", "Wrangler"],
    "Nissan": ["Magnite"],
}

_MODEL_INDEX = []
for _brand, _models in INDIAN_CAR_DATA.items():
    for _model in sorted(_models, key=len, reverse=True):
        _MODEL_INDEX.append((_brand, _model, re.compile(re.escape(_model), re.I)))

_BRAND_ALIASES = [
    ("Maruti Suzuki", re.compile(r"\bmaruti(\s+suzuki)?\b", re.I)),
    ("Hyundai", re.compile(r"\bhyundai\b", re.I)),
    ("Tata", re.compile(r"\btata\b", re.I)),
    ("Mahindra", re.compile(r"\bmahindra\b", re.I)),
    ("Kia", re.compile(r"\bkia\b", re.I)),
    ("Toyota", re.compile(r"\btoyota\b", re.I)),
    ("Honda", re.compile(r"\bhonda\b", re.I)),
    ("Renault", re.compile(r"\brenaul?t\b", re.I)),
    ("Volkswagen", re.compile(r"\b(volkswagen|vw)\b", re.I)),
    ("Skoda", re.compile(r"\bskoda\b", re.I)),
    ("MG", re.compile(r"\b(mg|morris garage)\b", re.I)),
    ("Jeep", re.compile(r"\bjeep\b", re.I)),
    ("Nissan", re.compile(r"\bnissan\b", re.I)),
]


def _parse_price(text: str) -> Optional[float]:
    t = text.replace(",", "")
    m = re.search(r"(?:rs\.?|₹|inr)\s*([\d.]+)\s*(cr|crore|lakh|lac|l)\b", t, re.I)
    if not m:
        m = re.search(r"([\d.]+)\s*(cr|crore|lakh|lac|l)\b", t, re.I)
    if m:
        n = float(m.group(1))
        unit = m.group(2).lower()
        if unit in ("cr", "crore"):
            return n * 10000000
        return n * 100000
    m = re.search(r"(?:rs\.?|₹|asking[^0-9]{0,12})(\d{5,8})", t, re.I)
    if m:
        return float(m.group(1))
    m = re.search(r"\b(\d{6,8})\b", t)
    if m:
        val = float(m.group(1))
        if 80000 <= val <= 80000000:
            return val
    return None


def _parse_km(text: str) -> Optional[int]:
    t = text.replace(",", "")
    m = re.search(r"(\d{2,7})\s*(?:km|kms|kilomet(?:er|re)s?)\b", t, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,3})\s*k\b", t, re.I)
    if m:
        n = int(m.group(1))
        if 5 <= n <= 400:
            return n * 1000
    return None


def _parse_year(text: str) -> Optional[int]:
    years = [int(y) for y in re.findall(r"\b(20[0-2]\d)\b", text)]
    years = [y for y in years if 2005 <= y <= 2026]
    return years[0] if years else None


def heuristic_extract(text: str, url: Optional[str] = None) -> Dict[str, Any]:
    blob = f"{url or ''}\n{text or ''}"
    slug = re.sub(r"[-_/]+", " ", blob)
    search_in = f"{blob} {slug}"

    brand = None
    model = None
    for b, m, rx in _MODEL_INDEX:
        if rx.search(search_in):
            brand, model = b, m
            break
    if not brand:
        for b, rx in _BRAND_ALIASES:
            if rx.search(search_in):
                brand = b
                break

    fuel = None
    if re.search(r"\bdiesel\b", search_in, re.I):
        fuel = "Diesel"
    elif re.search(r"\bcng\b", search_in, re.I):
        fuel = "CNG"
    elif re.search(r"\belectric\b|\bev\b", search_in, re.I):
        fuel = "Electric"
    elif re.search(r"\bpetrol\b", search_in, re.I):
        fuel = "Petrol"

    trans = None
    if re.search(r"\b(automatic|amt|cvt|dct|at)\b", search_in, re.I):
        trans = "Automatic"
    elif re.search(r"\b(manual|mt)\b", search_in, re.I):
        trans = "Manual"

    ownership = None
    if re.search(r"\b(first|1st|single)\s*owner\b", search_in, re.I):
        ownership = "First Owner"
    elif re.search(r"\b(second|2nd)\s*owner\b", search_in, re.I):
        ownership = "Second Owner"
    elif re.search(r"\b(third|3rd)\s*owner\b", search_in, re.I):
        ownership = "Third Owner"

    loc = None
    for city in ["Pune", "Mumbai", "Delhi", "Bengaluru", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Jaipur", "Surat", "Nagpur"]:
        if re.search(rf"\b{city}\b", search_in, re.I):
            loc = "Bengaluru" if city == "Bangalore" else city
            break

    return {
        "brand": brand,
        "model": model,
        "manufacturing_year": _parse_year(search_in),
        "kilometers_driven": _parse_km(search_in),
        "fuel_type": fuel,
        "transmission": trans,
        "ownership": ownership,
        "location": loc,
        "asking_price": _parse_price(search_in),
        "seller_description": (text or "")[:4000] or None,
        "listing_url": url,
    }


def groq_result_matches_source(extracted: Dict[str, Any], source_text: str) -> bool:
    if not extracted:
        return False
    blob = (source_text or "").lower()
    brand = str(extracted.get("brand") or "").strip()
    model = str(extracted.get("model") or "").strip()
    if brand and brand.lower() not in blob and brand.split()[0].lower() not in blob:
        return False
    if model:
        token = model.lower().split()[0]
        if len(token) >= 3 and token not in blob and model.lower() not in blob:
            return False
    return True


def merge_extract(heuristic: Dict[str, Any], groq_data: Optional[Dict[str, Any]], source_text: str) -> Dict[str, Any]:
    merged = {k: v for k, v in (heuristic or {}).items() if v not in (None, "")}
    if groq_data and groq_result_matches_source(groq_data, source_text):
        for k, v in groq_data.items():
            if v not in (None, "") and k not in merged:
                merged[k] = v
            elif v not in (None, "") and k in ("variant", "color", "body_type", "rto", "insurance_valid", "registration_year"):
                merged[k] = v
    return merged
