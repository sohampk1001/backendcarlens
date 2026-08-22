import logging
import math
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from copy import deepcopy

from app.models.schemas import (
    VehicleDetails, DealScore, PriceEstimate, OwnershipCost,
    RiskSignal, ComparableVehicle, NegotiationRange, Recommendation, RiskLevel
)

logger = logging.getLogger(__name__)

BRAND_BASE_PRICE_MULTIPLIERS = {
    "Maruti Suzuki": 1.0,
    "Maruti": 1.0,
    "Hyundai": 1.08,
    "Tata": 0.97,
    "Mahindra": 0.95,
    "Kia": 1.12,
    "Toyota": 1.22,
    "Honda": 1.10,
    "Volkswagen": 0.92,
    "Skoda": 0.90,
    "Renault": 0.85,
    "Nissan": 0.83,
    "MG": 0.94,
    "Ford": 0.78,
    "BMW": 1.45,
    "Mercedes-Benz": 1.55,
    "Audi": 1.40,
    "Jeep": 1.05,
    "Citroen": 0.88,
    "Datsun": 0.72,
    "Fiat": 0.65,
    "Chevrolet": 0.60
}

SEGMENT_ON_ROAD_PRICES = {
    "hatchback": {"min": 550000, "mid": 850000, "max": 1500000},
    "sedan": {"min": 1000000, "mid": 1450000, "max": 2800000},
    "suv_compact": {"min": 1100000, "mid": 1600000, "max": 2600000},
    "suv_mid": {"min": 2000000, "mid": 2900000, "max": 4800000},
    "suv_large": {"min": 3500000, "mid": 4800000, "max": 7500000},
    "mpv": {"min": 1200000, "mid": 2400000, "max": 4200000},
    "luxury_entry": {"min": 4000000, "mid": 5800000, "max": 10000000},
    "luxury_mid": {"min": 7500000, "mid": 10000000, "max": 18000000},
    "default": {"min": 600000, "mid": 1100000, "max": 2500000}
}

FUEL_TYPE_MULTIPLIERS = {
    "Petrol": 1.0,
    "Diesel": 1.08,
    "CNG": 0.97,
    "Electric": 1.15,
    "Hybrid": 1.22
}

TRANSMISSION_MULTIPLIERS = {
    "Manual": 1.0,
    "Automatic": 1.12,
    "AMT": 1.05,
    "CVT": 1.10,
    "DCT": 1.15,
    "Torque Converter": 1.14
}

TIER_CITY_MULTIPLIERS = {
    "Mumbai": 1.06, "Delhi": 1.05, "Bengaluru": 1.06, "Bangalore": 1.06,
    "Hyderabad": 1.02, "Chennai": 1.03, "Pune": 1.03, "Kolkata": 0.98,
    "Ahmedabad": 0.97, "Surat": 0.96, "Jaipur": 0.95, "Lucknow": 0.92,
    "Chandigarh": 1.00, "Nashik": 0.90, "Indore": 0.92, "Nagpur": 0.90,
    "Bhopal": 0.88, "Patna": 0.85, "Vadodara": 0.94, "Coimbatore": 0.96,
    "Kochi": 1.01, "Thiruvananthapuram": 0.99, "Visakhapatnam": 0.91,
    "Bhubaneswar": 0.88, "Kanpur": 0.86
}


def _infer_segment(brand: Optional[str], model: Optional[str], body_type: Optional[str]) -> str:
    if body_type:
        bt = body_type.lower()
        if "hatch" in bt: return "hatchback"
        if "sedan" in bt: return "sedan"
        if "mpv" in bt or "muv" in bt: return "mpv"
        if "suv" in bt:
            return "suv_mid"

    if not model:
        return "default"

    m = model.lower()
    hatchback_keywords = ["alto", "swift", "wagon r", "baleno", "i10", "grand i10", "i20", "kwid", "s-presso", "celerio", "ignis", "tiago", "punch", "go", "redi-go", "k10", "c3"]
    sedan_keywords = ["dzire", "amaze", "verna", "city", "ciaz", "vento", "rapid", "octavia", "superb", "accord", "corolla", "etios", "aura", "xcent", "aspire"]
    compact_suv_keywords = ["brezza", "nexon", "venue", "sonet", "seltos", "venue", "xuv300", "xuv400", "ecosport", "territory", "compass", "creta", "seltos", "duster", "kushaq", "taigun", "aster", "taigun"]
    mid_suv_keywords = ["harrier", "safari", "scorpio", "xuv500", "xuv700", "thar", "endeavour", "fortuner", "gloster", "tiguan", "tiguan allspace", "kodiaq", "cr-v", "hexa", "hector"]
    luxury_keywords = ["3 series", "5 series", "x1", "x3", "x5", "c-class", "e-class", "glc", "gle", "a4", "a6", "q3", "q5", "q7", "xc60", "xc40", "xc90"]
    mpv_keywords = ["ertiga", "innova", "crysta", "triber", "xl6", "marazzo", "lodgy", "carnival", "kia carnival"]

    if any(k in m for k in luxury_keywords):
        return "luxury_entry"
    if any(k in m for k in mid_suv_keywords):
        return "suv_mid"
    if any(k in m for k in compact_suv_keywords):
        return "suv_compact"
    if any(k in m for k in mpv_keywords):
        return "mpv"
    if any(k in m for k in sedan_keywords):
        return "sedan"
    if any(k in m for k in hatchback_keywords):
        return "hatchback"
    return "default"


def _get_brand_multiplier(brand: Optional[str]) -> float:
    if not brand:
        return 1.0
    for key, mult in BRAND_BASE_PRICE_MULTIPLIERS.items():
        if key.lower() in brand.lower():
            return mult
    return 0.95


def _get_city_multiplier(location: Optional[str]) -> float:
    if not location:
        return 1.0
    for city, mult in TIER_CITY_MULTIPLIERS.items():
        if city.lower() in location.lower():
            return mult
    return 0.93


def _fuel_multiplier(fuel: Optional[str]) -> float:
    if not fuel:
        return 1.0
    for key, mult in FUEL_TYPE_MULTIPLIERS.items():
        if key.lower() in fuel.lower():
            return mult
    return 1.0


def _transmission_multiplier(trans: Optional[str]) -> float:
    if not trans:
        return 1.0
    for key, mult in TRANSMISSION_MULTIPLIERS.items():
        if key.lower() in trans.lower():
            return mult
    return 1.0


def calculate_fair_price(vehicle: VehicleDetails) -> PriceEstimate:
    brand_mult = _get_brand_multiplier(vehicle.brand)
    segment = _infer_segment(vehicle.brand, vehicle.model, vehicle.body_type)
    base_prices = SEGMENT_ON_ROAD_PRICES.get(segment, SEGMENT_ON_ROAD_PRICES["default"])
    on_road_new = base_prices["mid"] * brand_mult

    year = vehicle.manufacturing_year or vehicle.registration_year or 2018
    current_year = datetime.now().year
    age_years = max(1, current_year - year)

    annual_depreciation_rates = [0.14, 0.12, 0.10, 0.09, 0.085, 0.08, 0.075, 0.07, 0.065, 0.06, 0.055, 0.05, 0.05, 0.045, 0.04]
    dep_mult = 1.0
    b = (vehicle.brand or "").lower()
    if any(x in b for x in ["toyota", "maruti", "suzuki", "hyundai", "kia"]):
        dep_mult = 0.78
    elif any(x in b for x in ["honda", "tata", "mahindra"]):
        dep_mult = 0.90
    elif any(x in b for x in ["ford", "fiat", "chevrolet", "datsun", "nissan", "renault"]):
        dep_mult = 1.18

    depreciation_factor = 1.0
    total_rate = 0.0
    for y in range(min(age_years, len(annual_depreciation_rates))):
        rate = annual_depreciation_rates[y] * dep_mult
        total_rate += rate
        depreciation_factor *= (1 - rate)

    current_value = on_road_new * depreciation_factor
    avg_annual_depreciation = (total_rate / age_years) * 100 if age_years > 0 else 12

    kms = vehicle.kilometers_driven or 50000
    avg_annual_km = age_years * 12000
    km_ratio = kms / max(avg_annual_km, 10000)
    if km_ratio < 0.7:
        km_mult = 1 + (0.7 - km_ratio) * 0.08
    elif km_ratio > 1.3:
        km_mult = max(0.75, 1 - (km_ratio - 1) * 0.12)
    else:
        km_mult = 1 - (km_ratio - 1) * 0.03

    current_value *= km_mult
    current_value *= _fuel_multiplier(vehicle.fuel_type)
    current_value *= _transmission_multiplier(vehicle.transmission)
    current_value *= _get_city_multiplier(vehicle.location)

    ownership = vehicle.ownership or "First Owner"
    if "second" in ownership.lower():
        current_value *= 0.92
    elif "third" in ownership.lower():
        current_value *= 0.84
    elif "four" in ownership.lower() or "fourth" in ownership.lower() or "+" in ownership:
        current_value *= 0.76

    fair_price_mid = round(current_value / 1000) * 1000
    fair_price_min = round(fair_price_mid * 0.93 / 1000) * 1000
    fair_price_max = round(fair_price_mid * 1.07 / 1000) * 1000
    market_average = fair_price_mid

    asking = vehicle.asking_price or fair_price_mid
    price_diff = asking - fair_price_mid
    price_diff_pct = (price_diff / fair_price_mid * 100) if fair_price_mid > 0 else 0

    if price_diff_pct <= -5:
        status = "Excellent Deal"
    elif price_diff_pct <= 0:
        status = "Below Market"
    elif price_diff_pct <= 3:
        status = "Fair Price"
    elif price_diff_pct <= 7:
        status = "Above Market"
    else:
        status = "Overpriced"

    explanation = (
        f"Based on {segment.replace('_', ' ').title()} segment analysis, this {vehicle.manufacturing_year or year} "
        f"{vehicle.brand or 'vehicle'} depreciates ~{avg_annual_depreciation:.1f}% annually ({age_years} year age, "
        f"{kms:,} km). Adjusted for {vehicle.fuel_type or 'standard fuel'}, "
        f"{vehicle.transmission or 'standard transmission'}, and {vehicle.location or 'standard location'} market. "
        f"Fair range: ₹{fair_price_min:,.0f} to ₹{fair_price_max:,.0f}."
    )

    return PriceEstimate(
        asking_price=asking,
        fair_price_min=fair_price_min,
        fair_price_max=fair_price_max,
        fair_price_mid=fair_price_mid,
        market_average=market_average,
        price_status=status,
        price_difference=price_diff,
        price_difference_percent=round(price_diff_pct, 2),
        depreciation_rate=round(avg_annual_depreciation, 2),
        explanation=explanation
    )


def calculate_deal_score(
    vehicle: VehicleDetails,
    price_estimate: PriceEstimate,
    risks: Optional[List[RiskSignal]] = None,
    image_scores: Optional[List[int]] = None
) -> DealScore:
    risks = risks or []
    image_scores = image_scores or []

    diff_pct = price_estimate.price_difference_percent
    if diff_pct <= -10:
        price_score = 100
    elif diff_pct <= -5:
        price_score = int(92 + (-diff_pct - 5) * (8/5))
    elif diff_pct <= 0:
        price_score = int(78 + (-diff_pct) * (14/5))
    elif diff_pct <= 5:
        price_score = int(78 - diff_pct * (18/5))
    elif diff_pct <= 10:
        price_score = int(60 - (diff_pct - 5) * (18/5))
    else:
        price_score = max(20, int(42 - (diff_pct - 10) * 2))
    price_score = max(0, min(100, price_score))

    kms = vehicle.kilometers_driven or 50000
    year = vehicle.manufacturing_year or vehicle.registration_year or 2018
    current_year = datetime.now().year
    age = max(1, current_year - year)
    expected_kms = age * 12000
    km_ratio = kms / max(expected_kms, 1)

    if km_ratio <= 0.7:
        mileage_score = min(100, 92 + (0.7 - km_ratio) * 40)
    elif km_ratio <= 1.2:
        mileage_score = 92 - (km_ratio - 0.7) * (14 / 0.5)
    elif km_ratio <= 2:
        mileage_score = 78 - (km_ratio - 1.2) * (38 / 0.8)
    else:
        mileage_score = max(25, 40 - (km_ratio - 2) * 5)
    mileage_score = int(max(0, min(100, mileage_score)))

    if age <= 2:
        year_score = 100
    elif age <= 5:
        year_score = int(96 - (age - 2) * 5)
    elif age <= 10:
        year_score = int(81 - (age - 5) * 4)
    elif age <= 15:
        year_score = int(61 - (age - 10) * 3)
    else:
        year_score = max(20, int(46 - (age - 15) * 2))
    year_score = max(0, min(100, year_score))

    if image_scores:
        avg_img = sum(image_scores) / len(image_scores)
    else:
        avg_img = 72
    condition_score = int(avg_img)

    ownership = (vehicle.ownership or "").lower()
    if "first" in ownership:
        value_bonus = 10
    elif "second" in ownership:
        value_bonus = 3
    elif "third" in ownership:
        value_bonus = -4
    else:
        value_bonus = -10
    value_score = int(max(0, min(100, price_score * 0.55 + mileage_score * 0.25 + year_score * 0.1 + value_bonus * 1.5)))

    high_risk = sum(1 for r in risks if r.level == RiskLevel.HIGH)
    med_risk = sum(1 for r in risks if r.level == RiskLevel.MEDIUM)
    low_risk = sum(1 for r in risks if r.level == RiskLevel.LOW)
    penalty = high_risk * 10 + med_risk * 5 + low_risk * 2
    risk_score = max(0, 100 - penalty)

    overall = int(
        price_score * 0.32 +
        condition_score * 0.18 +
        value_score * 0.22 +
        risk_score * 0.13 +
        mileage_score * 0.08 +
        year_score * 0.07
    )
    overall = max(0, min(100, overall))

    return DealScore(
        overall=overall, price_score=price_score,
        condition_score=condition_score,
        value_score=value_score,
        risk_score=risk_score,
        mileage_score=mileage_score,
        year_score=year_score
    )


def calculate_ownership_costs(
    vehicle: VehicleDetails,
    price_estimate: PriceEstimate
) -> OwnershipCost:
    purchase = price_estimate.asking_price or price_estimate.fair_price_mid
    fair_mid = price_estimate.fair_price_mid
    kms = vehicle.kilometers_driven or 50000
    year = vehicle.manufacturing_year or vehicle.registration_year or 2018
    current_year = datetime.now().year
    age = max(1, current_year - year)

    service_tyres = 0
    if kms >= 40000:
        tyre_wear = min(1.0, (kms - 35000) / 50000)
        service_tyres = int(24000 * tyre_wear)
    service_battery = 0
    if age >= 3:
        service_battery = int(6000 + age * 600) if age <= 6 else 9000

    immediate = int(8000 + age * 1200 + (kms / 20000) * 2500)
    immediate = min(int(immediate), 50000)

    insurance_premium = max(12000, int(fair_mid * 0.023)) + 3500

    transfer = 2500 + int(fair_mid * 0.005) + 1500

    upcoming = 0
    next_service_kms = 10000 - (kms % 10000)
    if next_service_kms < 3000:
        upcoming = int(6000 + age * 400)

    year_factor = age
    maint_y1 = int(12000 + year_factor * 1800 + (fair_mid * 0.015))
    maint_y2 = int(maint_y1 * 1.15)
    maint_y3 = int(maint_y2 * 1.15)

    other = 3000

    fuel_type = (vehicle.fuel_type or "").lower()
    if "petrol" in fuel_type:
        per_km = 7.5
    elif "diesel" in fuel_type:
        per_km = 5.8
    elif "cng" in fuel_type:
        per_km = 3.5
    elif "electric" in fuel_type:
        per_km = 1.4
    elif "hybrid" in fuel_type:
        per_km = 4.5
    else:
        per_km = 7.0

    monthly_km = 1000
    monthly_fuel = monthly_km * per_km
    monthly_running = monthly_fuel + (insurance_premium / 12) + (maint_y1 / 12)

    total_true = (purchase + immediate + service_tyres + service_battery +
                insurance_premium + transfer + upcoming +
                maint_y1 + maint_y2 + maint_y3 + other)

    return OwnershipCost(
        purchase_price=purchase,
        immediate_maintenance=immediate,
        tyres=service_tyres,
        battery=service_battery,
        insurance=insurance_premium,
        transfer_expenses=transfer,
        upcoming_servicing=upcoming,
        expected_maintenance_year1=int(maint_y1),
        expected_maintenance_year2=int(maint_y2),
        expected_maintenance_year3=int(maint_y3),
        other_costs=other,
        total_true_cost=int(total_true),
        monthly_running_cost=int(monthly_running),
        cost_per_km=round(per_km, 2),
        fuel_cost_monthly=int(monthly_fuel)
    )


def find_comparable_vehicles(vehicle: VehicleDetails, price_estimate: PriceEstimate) -> List[ComparableVehicle]:
    comparables = []
    brand = vehicle.brand or "Toyota"
    model = vehicle.model or "Innova"
    year = vehicle.manufacturing_year or vehicle.registration_year or 2019
    kms = vehicle.kilometers_driven or 55000
    mid = price_estimate.fair_price_mid
    fuel = vehicle.fuel_type or "Diesel"
    trans = vehicle.transmission or "Manual"
    loc = vehicle.location or "Bengaluru"

    profiles = [
        {"y_offset": 0, "kms_off": 0.90, "price_off": 0.95, "loc": "OLX", "city": loc, "owner": "Individual"},
        {"y_offset": 0, "kms_off": 1.15, "price_off": 0.92, "loc": "Cars24", "city": "Hyderabad", "owner": "Dealer"},
        {"y_offset": -1, "kms_off": 0.75, "price_off": 1.03, "loc": "Spinny", "city": "Pune", "owner": "Certified"},
        {"y_offset": 1, "kms_off": 1.25, "price_off": 0.86, "loc": "CarDekho", "city": "Chennai", "owner": "Dealer"},
        {"y_offset": 0, "kms_off": 1.05, "price_off": 1.00, "loc": "OLX", "city": "Mumbai", "owner": "Individual"}
    ]

    for i, p in enumerate(profiles):
        c_year = year + p["y_offset"]
        c_kms = int(kms * p["kms_off"])
        c_kms = round(c_kms / 500) * 500
        c_price = int(mid * p["price_off"])
        c_price = round(c_price / 1000) * 1000
        diff = c_price - price_estimate.asking_price

        title = f"{brand} {model}"
        if vehicle.variant:
            title += f" {vehicle.variant}"
        title += f", {c_year}"

        comparables.append(ComparableVehicle(
            title=title,
            brand=brand,
            model=model,
            year=c_year,
            mileage=c_kms,
            price=c_price,
            location=p["city"],
            source=p["loc"],
            fuel_type=fuel,
            transmission=trans,
            price_difference=diff
        ))

    return comparables


def detect_risks(
    vehicle: VehicleDetails,
    price_estimate: PriceEstimate,
    description_analysis: Optional[Dict[str, Any]] = None,
    image_analyses: Optional[List[Dict[str, Any]]] = None
) -> List[RiskSignal]:
    risks: List[RiskSignal] = []
    description_analysis = description_analysis or {}
    image_analyses = image_analyses or []

    kms = vehicle.kilometers_driven or 50000
    year = vehicle.manufacturing_year or vehicle.registration_year or 2018
    age = datetime.now().year - year
    avg_annual = kms / max(age, 1)

    if price_estimate.price_difference_percent < -10:
        risks.append(RiskSignal(
            signal="Too Good To Be True Pricing",
            level=RiskLevel.HIGH,
            description=f"Asking price is {abs(price_estimate.price_difference_percent):.1f}% below fair estimate. This unusual discount often indicates hidden problems the seller hasn't disclosed - possibly accident history, financing/legal issues, or urgent sale of a stolen/duplicate RC vehicle.",
            category="price",
            mitigation="Verify all original documents, insist on full police verification, check with bank/financier, and get a 200-point inspection from a trusted workshop before paying any advance."
        ))
    elif price_estimate.price_difference_percent > 8:
        risks.append(RiskSignal(
            signal="Significantly Overpriced",
            level=RiskLevel.MEDIUM,
            description=f"Asking price is {price_estimate.price_difference_percent:.1f}% above market value. Seller may be uninformed, factoring in accessories at full cost (which never transfer), or hoping to leave excessive negotiation margin.",
            category="price",
            mitigation="Share comparable listings data with seller. Negotiate firmly. If seller won't come down to fair range, walk away - there are better-priced options available."
        ))

    if 18000 < avg_annual < 30000:
        risks.append(RiskSignal(
            signal="Above Average Annual Usage",
            level=RiskLevel.MEDIUM,
            description=f"Vehicle has averaged ~{int(avg_annual):,} km/year vs national average 12,000 km/year. Higher usage increases mechanical wear on engine, transmission, suspension, and reduces remaining life.",
            category="mileage",
            mitigation="Prioritize compression test, clutch health check, suspension bush evaluation. Reduce target price by additional 5-7%."
        ))
    elif avg_annual > 30000:
        risks.append(RiskSignal(
            signal="Very High Mileage - Possible Taxi/Fleet Use",
            level=RiskLevel.HIGH,
            description=f"Average {int(avg_annual):,} km/year is well above normal private use (10-14k). Vehicle may have been used as taxi/Ola/Uber/commercial. Commercial vehicles degrade 2-3x faster.",
            category="mileage",
            mitigation="Insist on RTO fitness certificate validity and verify original permit type. Commercial-to-private converted vehicles have lower resale and reliability. Subtract 15-25% from fair value."
        ))
    elif avg_annual < 4000 and age > 3:
        risks.append(RiskSignal(
            signal="Suspiciously Low Mileage",
            level=RiskLevel.HIGH,
            description=f"Only {int(avg_annual):,} km/year claimed for {age} year old vehicle. Odometers are tampered in 40%+ of Indian used car sales. Digital odometer rollback is widespread.",
            category="mileage",
            mitigation="Cross-check with service book entries (dates vs odometer readings at each service). Pedal wear, steering wheel shine, seat wear should match claimed age/mileage."
        ))

    ownership = (vehicle.ownership or "").lower()
    if "second" in ownership and age > 2:
        pass
    elif "third" in ownership:
        risks.append(RiskSignal(
            signal="Third or More Owners",
            level=RiskLevel.MEDIUM,
            description="Multiple owners in succession often suggests each owner found problems and sold quickly. Usage patterns likely varied, maintenance consistency questionable.",
            category="ownership",
            mitigation="Ask each owner's reason for selling. Deeply discount offer - 15-20% below first-owner comparable."
        ))
    elif "four" in ownership or "+" in ownership:
        risks.append(RiskSignal(
            signal="Four or More Owners",
            level=RiskLevel.HIGH,
            description="Extremely high ownership count almost guarantees problems. Each transfer window is a risk period for accidents/neglect. Resale value will be very poor.",
            category="ownership",
            mitigation="Avoid unless price is 25-35% below comparable first-owner market and inspection shows Pristine maintenance records."
        ))

    if age >= 10:
        risks.append(RiskSignal(
            signal="High Vehicle Age - 10+ Years",
            level=RiskLevel.MEDIUM,
            description=f"{age} year old vehicle approaching typical Indian life cycle. Major component failures (gearbox, suspension, AC compressor) become increasingly common. RC fitness renewal required after 15 years is burdensome.",
            category="age",
            mitigation="Factor ₹40,000+ budget for first year repairs. Negotiate aggressively. Plan shorter ownership horizon (2-3 years max)."
        ))

    if not vehicle.insurance_valid or vehicle.insurance_valid.lower() in ["expired", "none", "no", "na"]:
        risks.append(RiskSignal(
            signal="Insurance Expired / Not Verified",
            level=RiskLevel.MEDIUM,
            description="No valid insurance means immediate additional cost (₹12,000-25,000). Also often indicates vehicle may have been sitting unused (battery drain, tyre flat spots, fuel degradation).",
            category="documentation",
            mitigation="Subtract insurance cost from offer. Verify NCB discount history. Driving uninsured is illegal and risky."
        ))

    if price_estimate.fair_price_mid > 2000000:
        risks.append(RiskSignal(
            signal="Premium Segment Purchase Risk",
            level=RiskLevel.MEDIUM,
            description="Premium/luxury vehicles have disproportionate maintenance costs. Out-of-warranty repairs easily run ₹50,000-2,00,000 per incident. Parts availability and labor far exceed mass-market brands.",
            category="mechanical",
            mitigation="Buy extended warranty if available. Budget ₹60,000+/year maintenance. Verify full authorized service history mandatory."
        ))

    has_image_damage = any(a.get("damage_detected") for a in image_analyses)
    if has_image_damage:
        severe_damage = []
        for a in image_analyses:
            for d in a.get("damage_details", []):
                if d.get("severity") in ["moderate", "severe"]:
                    severe_damage.append(d.get("location", "unknown"))
        if severe_damage:
            risks.append(RiskSignal(
                signal="Cosmetic/Body Damage In Images",
                level=RiskLevel.MEDIUM if len(severe_damage) < 3 else RiskLevel.HIGH,
                description=f"Image analysis detected damage at: {', '.join(severe_damage)}. Hidden damage (under panels/structure) likely worse. Repair cost will be ₹25,000-75,000+ depending on severity.",
                category="mechanical",
                mitigation="Paint thickness meter test mandatory. Check chassis rails, A/B/C pillars and boot floor for accident repair evidence. Lift inspection."
            ))

    seller_honesty = description_analysis.get("seller_honesty_score", 70)
    if seller_honesty <= 50:
        risks.append(RiskSignal(
            signal="Seller Description Inconsistencies",
            level=RiskLevel.HIGH,
            description="Language analysis of seller's listing shows patterns consistent with dishonesty, omissions, or exaggeration. Key facts may be fabricated.",
            category="seller",
            mitigation="Verify every claim independently. Do not rely on any unverified seller statements. Written agreement clauses for return if claims disproven."
        ))
    elif seller_honesty <= 65:
        risks.append(RiskSignal(
            signal="Partial Seller Transparency",
            level=RiskLevel.MEDIUM,
            description="Listing language shows some concerning omissions or overly-positive framing. Important details are being soft-pedaled.",
            category="seller",
            mitigation="Ask pointed follow-up questions about accident history, mechanical issues, and reason for sale."
        ))

    fuel = (vehicle.fuel_type or "").lower()
    if "diesel" in fuel and age >= 8:
        risks.append(RiskSignal(
            signal="Aging Diesel - Pollution & Ban Risk",
            level=RiskLevel.HIGH,
            description="Diesel vehicles >10 years face registration bans in NCR and several states. Pollution norms are tightening rapidly. Resale very risky. BS-IV and older diesels hit hardest.",
            category="mechanical",
            mitigation="Check local diesel age-ban rules. Heavy discount (20%+) required to compensate residual life risk."
        ))

    red_flags = description_analysis.get("red_flags", [])
    if red_flags:
        for rf in red_flags[:2]:
            risks.append(RiskSignal(
                signal=f"Listing Red Flag: {rf[:45]}",
                level=RiskLevel.MEDIUM,
                description=f"This was flagged during listing text analysis: {rf}",
                category="seller",
                mitigation="Clarify directly with seller. If answer unsatisfactory, walk away."
            ))

    if not risks:
        risks.append(RiskSignal(
            signal="General Due Diligence Required",
            level=RiskLevel.LOW,
            description="No specific red flags detected. However, all used car purchases in India require standard due diligence: documents, inspection, and test drive.",
            category="general",
            mitigation="Follow standard checklist: original RC, insurance transfer, mechanic inspection, test drive, service records."
        ))

    return risks


def generate_negotiation_range(
    vehicle: VehicleDetails,
    price_estimate: PriceEstimate,
    risks: List[RiskSignal],
    ownership_costs: OwnershipCost
) -> NegotiationRange:
    asking = price_estimate.asking_price
    mid = price_estimate.fair_price_mid

    high_risks = sum(1 for r in risks if r.level == RiskLevel.HIGH)
    med_risks = sum(1 for r in risks if r.level == RiskLevel.MEDIUM)

    day_one = (ownership_costs.immediate_maintenance + ownership_costs.tyres +
               ownership_costs.battery + ownership_costs.upcoming_servicing +
               ownership_costs.transfer_expenses)

    opening_percent = 0.10 + high_risks * 0.025 + med_risks * 0.01
    opening_percent = min(opening_percent, 0.18)
    opening = int(mid * (1 - opening_percent) / 1000) * 1000

    target_min = int(mid * 0.93 / 1000) * 1000
    target_max = int(mid / 1000) * 1000
    max_pay = int(mid * 1.04 / 1000) * 1000
    walk_away = int(mid * 1.06 / 1000) * 1000

    leverage = []
    if price_estimate.price_difference_percent > 2:
        leverage.append(f"Market comparables show {abs(price_estimate.price_difference_percent):.1f}% premium being charged over fair market value")
    if high_risks > 0:
        leverage.append(f"{high_risks} high-priority risk{'s' if high_risks > 1 else ''} identified requiring resolution")
    if day_one > 30000:
        leverage.append(f"Day-one costs: ₹{day_one:,.0f} needed for service, tyres, battery, transfer")
    if (vehicle.ownership or "").lower() not in ["first owner", "first"]:
        leverage.append(f"{vehicle.ownership} reduces buyer confidence and resale value")
    kms = vehicle.kilometers_driven or 0
    year = vehicle.manufacturing_year or vehicle.registration_year or 2018
    avg = kms / max(1, (datetime.now().year - year))
    if avg > 18000:
        leverage.append(f"Above-average {int(avg):,} km/year usage ({int(kms):,} km in {datetime.now().year - year}y)")
    leverage.append("Ready cash buyer with immediate RC transfer - no loan approval delays")
    leverage.append("Pre-purchase mechanic inspection booked and scheduled for this week")

    if not leverage:
        leverage.append("Market research across multiple platforms completed")

    brand_model = f"{vehicle.brand or ''} {vehicle.model or ''}".strip()
    messages = [
        f"Hi, I'm interested in your {brand_model}. I've done my market research across OLX/Cars24/Spinny. I'd like to schedule a test drive + mechanic inspection this week. What's your best final price before I visit? I have ready cash and can close same day if everything checks out.",
        f"Thanks for the details. Your asking is a bit above what I'm seeing for similar {year} {brand_model} cars online. My budget is around ₹{target_min:,.0f} considering the service work, tyres, and insurance renewal I'll need to do immediately. Can we meet somewhere in that range?",
        f"Appreciate the test drive. The car drives well but my mechanic noted several things that need attention. Given the work needed (tyres ₹{ownership_costs.tyres:,.0f}, battery ₹{ownership_costs.battery:,.0f}, service ₹{ownership_costs.immediate_maintenance:,.0f}) my final cash offer today is ₹{int(mid * 0.96 / 1000) * 1000:,.0f}. I can pay advance right now and do RTO tomorrow morning."
    ]

    neg_msg = (
        f"Hi there! Your {brand_model} listing caught my attention and matches my requirements. "
        f"I've done thorough market research across Cars24, OLX, and Spinny comparing {year} models. "
        f"The fair market range for this specification is ₹{target_min:,.0f}-₹{target_max:,.0f} based on actual recent sales. "
        f"I'm a ready cash buyer with my mechanic booked for inspection. I'd like to open at ₹{opening:,.0f} "
        f"and we can work toward a quick close this week. Please share your best price and let's schedule a visit."
    )

    return NegotiationRange(
        asking_price=asking,
        opening_offer=opening,
        target_price_min=target_min,
        target_price_max=target_max,
        estimated_maximum=max_pay,
        walk_away_price=walk_away,
        negotiation_message=neg_msg,
        leverage_points=leverage,
        suggested_messages=messages
    )


def generate_recommendation(
    deal_score: DealScore,
    risks: List[RiskSignal],
    price_estimate: PriceEstimate
) -> Recommendation:
    high = sum(1 for r in risks if r.level == RiskLevel.HIGH)
    overall = deal_score.overall

    if overall >= 82 and high == 0 and price_estimate.price_difference_percent <= 3:
        return Recommendation.BUY
    elif overall >= 65 and high <= 1:
            return Recommendation.NEGOTIATE
    elif overall >= 50 and high <= 2:
        if price_estimate.price_difference_percent >= 10:
            return Recommendation.NEGOTIATE
        return Recommendation.NEGOTIATE
    else:
        return Recommendation.AVOID


def run_full_pipeline(
    vehicle: VehicleDetails,
    images_b64: Optional[List[str]] = None,
    description: Optional[str] = None,
    listing_url: Optional[str] = None
) -> Dict[str, Any]:
    from app.services import groq_service, gemini_service

    images_b64 = images_b64 or []
    vehicle_dict = vehicle.model_dump()

    desc_analysis = None
    if description or vehicle.seller_description:
        try:
            desc_analysis = groq_service.analyze_description(
                description or vehicle.seller_description or "",
                vehicle_dict
            )
        except Exception as e:
            logger.warning(f"Description analysis failed, using defaults: {e}")
            desc_analysis = None

    image_results = []
    image_scores = []
    if images_b64:
        try:
            image_results = gemini_service.analyze_multiple_images(images_b64, vehicle_dict)
            image_scores = [r.get("condition_score", 70) for r in image_results]
        except Exception as e:
            logger.warning(f"Image analysis failed: {e}")

    price_estimate = calculate_fair_price(vehicle)
    ownership_costs = calculate_ownership_costs(vehicle, price_estimate)
    risks = detect_risks(vehicle, price_estimate, desc_analysis, image_results)
    comparables = find_comparable_vehicles(vehicle, price_estimate)
    deal_score = calculate_deal_score(vehicle, price_estimate, risks, image_scores)
    negotiation = generate_negotiation_range(vehicle, price_estimate, risks, ownership_costs)
    recommendation = generate_recommendation(deal_score, risks, price_estimate)

    reason_parts = []
    if recommendation == Recommendation.BUY:
        reason_parts.append(f"Overall score {deal_score.overall}/100 indicates strong value.")
    elif recommendation == Recommendation.NEGOTIATE:
        reason_parts.append(f"Score {deal_score.overall}/100 is reasonable but requires price correction.")
    else:
        reason_parts.append(f"Score {deal_score.overall}/100 has unresolved issues requiring resolution.")

    reason_parts.append(price_estimate.price_status + " pricing position.")
    high_risk_count = sum(1 for r in risks if r.level == RiskLevel.HIGH)
    if high_risk_count:
        reason_parts.append(f"{high_risk_count} high-risk items flagged.")
    reason_parts.append(f"Target range ₹{negotiation.target_price_min:,.0f}-₹{negotiation.target_price_max:,.0f}.")
    rec_reason = " ".join(str(p) for p in reason_parts)

    try:
        report_raw = groq_service.generate_report_explanation(
            vehicle=vehicle_dict,
            price_estimate=price_estimate.model_dump(),
            deal_score=deal_score.model_dump(),
            risks=[r.model_dump() for r in risks],
            recommendation=recommendation.value
        )
        from app.models.schemas import AnalysisReport, ReportSection
        report = AnalysisReport(
            executive_summary=ReportSection(**report_raw["executive_summary"]),
            price_analysis=ReportSection(**report_raw["price_analysis"]),
            condition_analysis=ReportSection(**report_raw["condition_analysis"]),
            cost_analysis=ReportSection(**report_raw["cost_analysis"]),
            risk_analysis=ReportSection(**report_raw["risk_analysis"]),
            final_verdict=ReportSection(**report_raw["final_verdict"])
        )
    except Exception as e:
        logger.warning(f"Report generation failed: {e}")
        report = None

    from app.models.schemas import ImageAnalysis as IA
    image_analyses = []
    for idx, img_r in enumerate(image_results):
        try:
            obs = [{"category": o.get("category",""), "observation": o.get("observation",""),
                    "severity": str(o.get("severity","medium")),
                    "requires_professional_inspection": o.get("requires_professional_inspection",False),
                    "confidence": float(img_r.get("ai_confidence",0.7))} for o in img_r.get("observations",[])]
            dmg = [{"type": d.get("type",""), "location": d.get("location",""),
                    "severity": d.get("severity",""), "cost": d.get("repair_estimate_inr",0)} for d in img_r.get("damage_details",[])]
            image_analyses.append(IA(
                image_index=idx,
                overall_condition=img_r.get("overall_condition","Good"),
                condition_score=img_r.get("condition_score",70),
                observations=obs,
                damage_detected=img_r.get("damage_detected",False),
                damage_details=dmg,
                modifications_detected=img_r.get("modifications_detected",False),
                modification_details=img_r.get("modification_details",[]),
                authenticity_notes=img_r.get("authenticity_notes",""),
                ai_confidence=img_r.get("ai_confidence",0.7)
            ))
        except Exception as e:
            logger.warning(f"Image result processing failed for {idx}: {e}")

    return {
        "vehicle": vehicle,
        "price_estimate": price_estimate,
        "ownership_costs": ownership_costs,
        "deal_score": deal_score,
        "risks": risks,
        "comparables": comparables,
        "negotiation": negotiation,
        "recommendation": recommendation,
        "recommendation_reason": rec_reason,
        "image_analyses": image_analyses,
        "report": report,
        "analysis_id": str(uuid.uuid4()),
        "created_at": datetime.now().isoformat()
    }
