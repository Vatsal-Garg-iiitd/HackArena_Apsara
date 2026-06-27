from pydantic import BaseModel, Field
from typing import List, Literal, Optional

# --- Tier 1A: Quant Synthesizer Schema ---

class SolvencyRead(BaseModel):
    trend: Literal["improving", "stable", "deteriorating"]
    rationale: str

class EfficiencyRead(BaseModel):
    trend: Literal["efficient", "lagging", "neutral"]
    rationale: str

class ProfitabilityRead(BaseModel):
    strength: Literal["strong", "weak", "stable"]
    rationale: str

class SmartMoneyRead(BaseModel):
    signal: Literal["accumulating", "distributing", "neutral"]
    rationale: str

class TechnicalRead(BaseModel):
    signal: Literal["overbought", "oversold", "neutral"]
    rationale: str

class MacroFit(BaseModel):
    fit: Literal["tailwind", "headwind", "neutral"] = Field(alias="tailwind|headwind|neutral")
    rationale: str

class QuantSynthesizerOutput(BaseModel):
    ticker: str
    solvency_read: SolvencyRead
    efficiency_read: EfficiencyRead
    profitability_read: ProfitabilityRead
    smart_money_read: SmartMoneyRead
    technical_read: TechnicalRead
    macro_fit: MacroFit

class QuantSynthesizerBatch(BaseModel):
    results: List[QuantSynthesizerOutput]

# --- Tier 1B: Narrative Synthesizer Schema ---

class NewsSentiment(BaseModel):
    tone: Literal["positive", "negative", "mixed", "neutral"]
    key_drivers: List[str]

class EarningsRead(BaseModel):
    tone: Literal["positive", "negative", "mixed", "neutral"]
    guidance_direction: Literal["raised", "maintained", "lowered", "none_given"]
    key_quotes_paraphrased: List[str]

class Outlook(BaseModel):
    summary: str
    risk_flags: List[str]

class CompetitivePosition(BaseModel):
    summary: str
    relative_strength: Literal["gaining", "losing", "stable"]

class NarrativeSynthesizerOutput(BaseModel):
    ticker: str
    news_sentiment: NewsSentiment
    earnings_read: EarningsRead
    outlook: Outlook
    competitive_position: CompetitivePosition

# --- Tier 2: General Expert Schema ---

class HorizonSignals(BaseModel):
    tactical_horizon_30d: Literal["buy", "hold", "sell"] = Field(description="Short-term alpha signals based on technicals and momentum")
    structural_horizon_1y: Literal["buy", "hold", "sell"] = Field(description="Long-term core health based on balance sheet solvency and margins")

class GeneralExpertOutput(BaseModel):
    ticker: str
    signals: HorizonSignals
    confidence: Literal["low", "medium", "high"]
    rationale: str
    conflicting_signals: List[str]
    
class GeneralExpertBatch(BaseModel):
    results: List[GeneralExpertOutput]
