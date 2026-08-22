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
    color: Optional[str] = None
    body_type: Optional[str] = None
    insurance_valid: Optional[str] = None
    rto: Optional[str] = None


class AnalysisRequest(BaseModel):
    listing_url: Optional[str] = None
    vehicle_details: Optional[VehicleDetails] = None
    images: Optional[List[str]] = None
    description: Optional[str] = None


class DealScore(BaseModel):
    overall: int = Field(0, ge=0, le=100)
    price_score: int = Field(0, ge=0, le=100)
    condition_score: int = Field(0, ge=0, le=100)
    value_score: int = Field(0, ge=0, le=100)
    risk_score: int = Field(0, ge=0, le=100)
    mileage_score: int = Field(0, ge=0, le=100)
    year_score: int = Field(0, ge=0, le=100)


class PriceEstimate(BaseModel):
    asking_price: float = 0
    fair_price_min: float = 0
    fair_price_max: float = 0
    fair_price_mid: float = 0
    market_average: float = 0
    price_status: str = "N/A"
    price_difference: float = 0
    price_difference_percent: float = 0
    depreciation_rate: float = 0
    explanation: str = ""


class OwnershipCost(BaseModel):
    purchase_price: float = 0
    immediate_maintenance: float = 0
    tyres: float = 0
    battery: float = 0
    insurance: float = 0
    transfer_expenses: float = 0
    upcoming_servicing: float = 0
    expected_maintenance_year1: float = 0
    expected_maintenance_year2: float = 0
    expected_maintenance_year3: float = 0
    other_costs: float = 0
    total_true_cost: float = 0
    monthly_running_cost: float = 0
    cost_per_km: float = 0
    fuel_cost_monthly: float = 0


class RiskSignal(BaseModel):
    signal: str
    level: RiskLevel = RiskLevel.MEDIUM
    description: str
    category: str = "general"
    mitigation: Optional[str] = None


class ComparableVehicle(BaseModel):
    title: str
    brand: str
    model: str
    year: int
    mileage: int
    price: float
    location: str
    source: str
    fuel_type: Optional[str] = None
    transmission: Optional[str] = None
    price_difference: Optional[float] = None


class NegotiationRange(BaseModel):
    asking_price: float = 0
    opening_offer: float = 0
    target_price_min: float = 0
    target_price_max: float = 0
    estimated_maximum: float = 0
    walk_away_price: float = 0
    negotiation_message: str = ""
    leverage_points: List[str] = []
    suggested_messages: List[str] = []


class ImageAnalysis(BaseModel):
    image_index: int
    overall_condition: str = "Good"
    condition_score: int = 70
    observations: List[Dict[str, Any]] = []
    damage_detected: bool = False
    damage_details: List[Dict[str, Any]] = []
    modifications_detected: bool = False
    modification_details: List[str] = []
    authenticity_notes: str = ""
    ai_confidence: float = 0.75


class SavedVehicle(BaseModel):
    id: Optional[str] = None
    vehicle: VehicleDetails
    analysis_id: Optional[str] = None
    saved_at: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class ComparisonRequest(BaseModel):
    vehicles: List[VehicleDetails]
    metrics: Optional[List[str]] = None


class ComparisonItem(BaseModel):
    vehicle: VehicleDetails
    price_estimate: PriceEstimate
    deal_score: DealScore
    ownership_costs: OwnershipCost
    risks: List[RiskSignal]
    rank: int = 0


class ComparisonResult(BaseModel):
    vehicles: List[ComparisonItem]
    recommendation_index: int = 0
    summary: str = ""
    winner_reason: str = ""


class ReportSection(BaseModel):
    title: str
    content: str
    key_points: List[str] = []


class AnalysisReport(BaseModel):
    executive_summary: ReportSection
    price_analysis: ReportSection
    condition_analysis: ReportSection
    cost_analysis: ReportSection
    risk_analysis: ReportSection
    final_verdict: ReportSection


class AnalysisResult(BaseModel):
    vehicle: VehicleDetails
    price_estimate: PriceEstimate
    ownership_costs: OwnershipCost
    deal_score: DealScore
    risks: List[RiskSignal] = []
    comparables: List[ComparableVehicle] = []
    negotiation: NegotiationRange
    recommendation: Recommendation = Recommendation.NEGOTIATE
    recommendation_reason: str = ""
    image_analyses: List[ImageAnalysis] = []
    report: Optional[AnalysisReport] = None
    analysis_id: str = ""
    created_at: str = ""
