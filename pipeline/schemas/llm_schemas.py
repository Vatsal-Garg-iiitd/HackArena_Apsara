from pydantic import BaseModel, Field
from typing import List, Literal, Optional


# --- Uncertainty Quantification ---

class SignalWithConfidence(BaseModel):
    """Every signal output includes structured uncertainty quantification."""
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0, description="0.0 to 1.0 where 1.0 = all evidence strongly supports")
    corroborating_signals: List[str] = Field(default_factory=list, description="Specific data points supporting this conclusion")
    contradicting_signals: List[str] = Field(default_factory=list, description="Data points contradicting, even if conclusion holds")
    data_quality_score: float = Field(ge=0.0, le=1.0, default=1.0, description="0.0 = critical data missing, 1.0 = all data clean")


# --- Tier 1A: Quant Synthesizer Schema ---

class SolvencyRead(BaseModel):
    trend: Literal["improving", "stable", "deteriorating"]
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EfficiencyRead(BaseModel):
    trend: Literal["efficient", "lagging", "neutral"]
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class ProfitabilityRead(BaseModel):
    strength: Literal["strong", "weak", "stable"]
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class SmartMoneyRead(BaseModel):
    signal: Literal["accumulating", "distributing", "neutral"]
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class TechnicalRead(BaseModel):
    signal: Literal["overbought", "oversold", "neutral"]
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class MacroFit(BaseModel):
    fit: Literal["tailwind", "headwind", "neutral"] = Field(alias="tailwind|headwind|neutral")
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class FactorExposureRead(BaseModel):
    """LLM interpretation of factor decomposition."""
    alpha_interpretation: str = ""
    factor_adjusted_view: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class QuantSynthesizerOutput(BaseModel):
    ticker: str
    solvency_read: SolvencyRead
    efficiency_read: EfficiencyRead
    profitability_read: ProfitabilityRead
    smart_money_read: SmartMoneyRead
    technical_read: TechnicalRead
    macro_fit: MacroFit
    factor_exposure_read: Optional[FactorExposureRead] = None
    data_quality_score: float = Field(ge=0.0, le=1.0, default=1.0, description="Overall data quality for this ticker")


class QuantSynthesizerBatch(BaseModel):
    results: List[QuantSynthesizerOutput]


# --- Tier 1B: Narrative Synthesizer Schema ---

class NewsSentiment(BaseModel):
    tone: Literal["positive", "negative", "mixed", "neutral"]
    key_drivers: List[str]
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EarningsRead(BaseModel):
    tone: Literal["positive", "negative", "mixed", "neutral"]
    guidance_direction: Literal["raised", "maintained", "lowered", "none_given"]
    key_quotes_paraphrased: List[str]
    management_hedging_detected: bool = False
    analyst_concerns: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Outlook(BaseModel):
    summary: str
    risk_flags: List[str]
    new_risks_vs_prior: List[str] = Field(default_factory=list, description="Risks that appeared this quarter but not last")
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class CompetitivePosition(BaseModel):
    summary: str
    relative_strength: Literal["gaining", "losing", "stable"]
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class NarrativeSynthesizerOutput(BaseModel):
    ticker: str
    news_sentiment: NewsSentiment
    earnings_read: EarningsRead
    outlook: Outlook
    competitive_position: CompetitivePosition
    data_quality_score: float = Field(ge=0.0, le=1.0, default=1.0)


# --- Tier 2: General Expert Schema ---

class HorizonSignals(BaseModel):
    tactical_horizon_30d: SignalWithConfidence = Field(description="Short-term alpha signals based on technicals and momentum")
    structural_horizon_1y: SignalWithConfidence = Field(description="Long-term core health based on balance sheet solvency and margins")


class GeneralExpertOutput(BaseModel):
    ticker: str
    signals: HorizonSignals
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.5, description="Overall confidence combining all signals")
    rationale: str
    conflicting_signals: List[str]
    data_quality_score: float = Field(ge=0.0, le=1.0, default=1.0)
    macro_regime_adjustment: Optional[str] = None
    consistency_flags: List[str] = Field(default_factory=list, description="Flags from semantic consistency checker")


class GeneralExpertBatch(BaseModel):
    results: List[GeneralExpertOutput]
