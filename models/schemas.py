from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Recommendation(str, Enum):
    BUY = "BUY"
    NEGOTIATE = "NEGOTIATE"
    AVOID = "AVOID"


class VehicleDetails(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    variant: Optional[str] = None
    manufacturing_year: Optional[int] = None
    registration_year: Optional[int] = None
    kilometers_driven: Optional[int] = None
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    ownership: Optional[str] = None
    location: Optional[str] = None
    asking_price: Optional[float] = None
    seller_description: Optional[str] = None
    listing_url: Optional[str] = None


class FairPriceEstimate(BaseModel):
    asking_price: float
    fair_price_min: float
    fair_price_max: float
    fair_price_mid: float
    price_status: str
    price_difference: float
    price_difference_percent: float
    explanation: str


class OwnershipCostBreakdown(BaseModel):
    purchase_price: float
    immediate_maintenance: float
    tyres: float
    battery: float
    insurance: float
    transfer_expenses: float
    upcoming_servicing: float
    expected_maintenance: float
    other_costs: float
    total_true_cost: float


class VisualObservation(BaseModel):
    category: str
    observation: str
    severity: RiskLevel
    requires_professional_inspection: bool
    confidence: float


class RiskSignal(BaseModel):
    signal: str
    level: RiskLevel
    description: str


class DealScore(BaseModel):
    overall: int
    price_score: int
    condition_score: int
    value_score: int
    risk_score: int


class NegotiationRange(BaseModel):
    asking_price: float
    opening_offer: float
    target_price_min: float
    target_price_max: float
    estimated_maximum: float
    negotiation_message: str


class ComparableVehicle(BaseModel):
    title: str
    year: int
    mileage: int
    price: float
    location: str
    source: str


class CarAnalysisResult(BaseModel):
    vehicle_details: VehicleDetails
    fair_price_estimate: FairPriceEstimate
    ownership_costs: OwnershipCostBreakdown
    visual_observations: List[VisualObservation]
    risk_signals: List[RiskSignal]
    deal_score: DealScore
    negotiation: NegotiationRange
    comparable_vehicles: List[ComparableVehicle]
    overall_recommendation: Recommendation
    recommendation_reason: str
    ai_explanation: str


class AnalysisStage(BaseModel):
    stage: str
    status: str
    message: str


class AnalyzeCarRequest(BaseModel):
    listing_url: Optional[str] = None
    manual_details: Optional[VehicleDetails] = None
    image_count: int = 0
