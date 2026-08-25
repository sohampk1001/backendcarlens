"""
Indian car market data — May 2026 sales figures and pricing context.
Used to enrich AI analysis with real market demand signals.
"""

# May 2026 Top Selling Models (units sold) — used for demand scoring
# Higher sales = stronger resale demand = better value retention
MAY_2026_SALES = {
    "Maruti Suzuki Wagon R": 18500,
    "Maruti Suzuki Swift": 15800,
    "Maruti Suzuki Baleno": 14200,
    "Maruti Suzuki Dzire": 13900,
    "Maruti Suzuki Brezza": 13100,
    "Maruti Suzuki Ertiga": 10200,
    "Hyundai Creta": 16100,
    "Hyundai Venue": 10500,
    "Hyundai Grand i10 Nios": 8400,
    "Hyundai i20": 7900,
    "Tata Nexon": 14500,
    "Tata Punch": 13800,
    "Tata Tiago": 7600,
    "Tata Harrier": 5200,
    "Tata Safari": 4800,
    "Mahindra Scorpio-N": 9800,
    "Mahindra Thar": 7500,
    "Mahindra XUV700": 8900,
    "Mahindra Bolero": 10100,
    "Kia Seltos": 9200,
    "Kia Sonet": 7400,
    "Toyota Innova Crysta": 5100,
    "Toyota Innova HyCross": 4600,
    "Toyota Fortuner": 3100,
    "Honda City": 3800,
    "MG Hector": 2900,
    "Renault Kwid": 4200,
    "Nissan Magnite": 3500,
    "Volkswagen Taigun": 2800,
    "Skoda Kushaq": 2600,
    "Tata Nexon EV": 4100,
    "Tata Tiago EV": 2700,
    "MG Windsor EV": 3200,
    "Mahindra BE 6e": 2400,
}

# Annual depreciation rates by segment (percentage per year)
DEPRECIATION_RATES = {
    "hatchback":    {"petrol": 13, "diesel": 14, "electric": 18, "cng": 12},
    "sedan":        {"petrol": 14, "diesel": 15, "electric": 19, "cng": 13},
    "suv":          {"petrol": 12, "diesel": 13, "electric": 17, "cng": 11},
    "mpv":          {"petrol": 14, "diesel": 13, "electric": 18, "cng": 13},
    "luxury":       {"petrol": 18, "diesel": 18, "electric": 22, "cng": 17},
    "default":      {"petrol": 14, "diesel": 14, "electric": 19, "cng": 13},
}

# City-wise price premium/discount (% adjustment to base price)
CITY_PRICE_FACTORS = {
    "mumbai": 3, "delhi": 2, "bangalore": 2, "bengaluru": 2,
    "hyderabad": 1, "chennai": 1, "pune": 1, "ahmedabad": 0,
    "kolkata": -1, "jaipur": -2, "lucknow": -2, "surat": -1,
    "nagpur": -3, "bhopal": -3, "indore": -2, "patna": -4,
    "chandigarh": -1, "kochi": 1, "coimbatore": -2, "default": 0,
}

# High-demand models (get 5% price premium in used market)
HIGH_DEMAND_MODELS = [
    "creta", "nexon", "punch", "thar", "scorpio-n", "xuv700",
    "seltos", "brezza", "baleno", "swift", "fortuner", "innova",
    "harrier", "safari", "sonet", "venue", "hyryder", "grand vitara",
]

# Segment classification
BODY_TYPE_SEGMENTS = {
    "hatchback": "hatchback",
    "sedan": "sedan",
    "suv": "suv", "crossover": "suv", "compact suv": "suv",
    "mpv": "mpv", "muv": "mpv", "van": "mpv",
    "luxury": "luxury", "premium": "luxury",
}


def get_demand_score(brand: str, model: str) -> int:
    """Return 0-100 demand score based on sales data."""
    key = f"{brand} {model}".strip()
    # exact match
    sales = MAY_2026_SALES.get(key, 0)
    if not sales:
        # partial match
        for k, v in MAY_2026_SALES.items():
            if model.lower() in k.lower() or (brand and brand.lower() in k.lower() and model.lower() in k.lower()):
                sales = v
                break
    if sales >= 15000: return 95
    if sales >= 10000: return 85
    if sales >= 7000:  return 75
    if sales >= 5000:  return 65
    if sales >= 3000:  return 55
    if sales >= 1000:  return 45
    return 40


def get_depreciation_rate(body_type: str, fuel_type: str, age_years: int) -> float:
    """Return effective cumulative depreciation % for given age."""
    segment = BODY_TYPE_SEGMENTS.get((body_type or "").lower(), "default")
    fuel = (fuel_type or "petrol").lower()
    if "electric" in fuel: fuel_key = "electric"
    elif "diesel" in fuel: fuel_key = "diesel"
    elif "cng" in fuel:    fuel_key = "cng"
    else:                  fuel_key = "petrol"
    annual = DEPRECIATION_RATES.get(segment, DEPRECIATION_RATES["default"]).get(fuel_key, 14)
    # Accelerated first year, then reducing balance
    cum = 0
    remaining = 100.0
    for yr in range(int(age_years)):
        rate = annual * (1.3 if yr == 0 else 1.0)
        dep = remaining * (rate / 100)
        cum += dep
        remaining -= dep
    return round(min(cum, 75), 1)  # cap at 75%


def get_city_factor(location: str) -> float:
    """Return price adjustment factor for city."""
    if not location:
        return 1.0
    loc_lower = location.lower()
    for city, pct in CITY_PRICE_FACTORS.items():
        if city in loc_lower:
            return 1 + (pct / 100)
    return 1.0


def is_high_demand(model: str) -> bool:
    if not model:
        return False
    return any(m in model.lower() for m in HIGH_DEMAND_MODELS)


def get_market_context_summary() -> str:
    """Return a text summary for AI prompts."""
    top5 = sorted(MAY_2026_SALES.items(), key=lambda x: x[1], reverse=True)[:5]
    top5_str = ", ".join(f"{k} ({v:,} units)" for k, v in top5)
    return (
        f"Indian car market context (May 2026): "
        f"Top selling models: {top5_str}. "
        f"SUV segment dominates with 45%+ market share. "
        f"EV adoption growing — Nexon EV, Windsor EV, BE 6e leading. "
        f"Diesel vehicles facing lower demand in metros due to emission norms. "
        f"Used car prices 8-12% higher than pre-2024 due to chip shortage legacy inventory. "
        f"Average used car transaction price: ₹8.2L. "
        f"OLX, CarWale, CarDekho, Spinny, CARS24 are dominant platforms."
    )
