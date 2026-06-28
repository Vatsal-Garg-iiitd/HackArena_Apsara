from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import date


class SolvencyMetrics(BaseModel):
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    cash_ratio: Optional[float] = None
    op_cash_flow_ratio: Optional[float] = None
    working_cap: Optional[float] = None
    debt_equity: Optional[float] = None
    debt_ratio: Optional[float] = None
    equity_ratio: Optional[float] = None
    debt_capital: Optional[float] = None
    interest_coverage: Optional[float] = None
    fixed_charge_coverage: Optional[float] = None
    cash_flow_debt: Optional[float] = None
    trend_8q: List[float] = Field(default_factory=list)  # trend of current ratio


class EfficiencyMetrics(BaseModel):
    inventory_turnover: Optional[float] = None
    receivables_turnover: Optional[float] = None
    payables_turnover: Optional[float] = None
    dso: Optional[float] = None


class ProfitabilityMetrics(BaseModel):
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roa: Optional[float] = None
    roe: Optional[float] = None
    roce: Optional[float] = None
    eps: Optional[float] = None
    roi: Optional[float] = None


class InvestorBehavior(BaseModel):
    institutional_delta_pct: Optional[float] = None
    insider_buys_90d: int = 0
    insider_sells_90d: int = 0
    short_interest_delta_pct: Optional[float] = None


class RollingSharpe(BaseModel):
    """Rolling Sharpe ratio distribution over 252-day windows."""
    current: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    window_count: int = 0


class MaxDrawdownDetail(BaseModel):
    """Detailed drawdown with recovery time."""
    full_period: Optional[float] = None
    full_period_recovery_days: Optional[int] = None
    per_year: Dict[str, float] = Field(default_factory=dict)


class Technicals(BaseModel):
    rsi_14: Optional[float] = None
    macd_signal: str = "neutral"
    volatility_annualized: Optional[float] = None
    # Improved Sharpe: rolling distribution instead of single point estimate
    sharpe_rolling: Optional[RollingSharpe] = None
    # Legacy field kept for backward compatibility
    sharpe_60d: Optional[float] = None
    # Detailed drawdown
    max_drawdown: Optional[MaxDrawdownDetail] = None
    # Legacy field kept for backward compatibility
    max_drawdown_60d: Optional[float] = None
    # Risk-free rate used
    risk_free_rate: Optional[float] = None
    # Data window info
    data_days: int = 0


class PeerDynamics(BaseModel):
    peer_tickers: List[str] = Field(default_factory=list)
    relative_sharpe: Optional[float] = None
    relative_volatility: Optional[float] = None
    relative_drawdown: Optional[float] = None
    # New: percentile rank and confidence
    percentile_rank_sharpe: Optional[float] = None
    percentile_rank_volatility: Optional[float] = None
    peer_count: int = 0
    peer_confidence: Optional[float] = None  # 0-1, based on peer count and distribution tightness


class NormalizedMetrics(BaseModel):
    current_ratio_vs_peers: Optional[float] = None
    debt_equity_vs_peers: Optional[float] = None
    gross_margin_vs_peers: Optional[float] = None
    roe_vs_peers: Optional[float] = None
    # New: macro regime context
    macro_regime: Optional[str] = None


class FactorExposureReport(BaseModel):
    """Fama-French 5-factor + Momentum decomposition."""
    alpha_annualized: Optional[float] = None
    alpha_t_statistic: Optional[float] = None
    alpha_significant: Optional[bool] = None  # t-stat > 2.0
    market_beta: Optional[float] = None
    size_loading: Optional[float] = None  # positive = small cap tilt
    value_loading: Optional[float] = None  # positive = value tilt
    profitability_loading: Optional[float] = None
    investment_loading: Optional[float] = None
    momentum_loading: Optional[float] = None
    r_squared: Optional[float] = None
    residual_volatility: Optional[float] = None


class OptionsSignals(BaseModel):
    """Options-derived forward-looking signals."""
    iv_rank: Optional[float] = None  # Current IV percentile in 52-week range
    put_call_ratio_volume: Optional[float] = None
    put_call_ratio_oi: Optional[float] = None
    put_skew: Optional[float] = None  # 25-delta put vs call skew
    term_structure: str = "normal"  # normal, backwardation, flat
    iv_at_money: Optional[float] = None
    near_term_event_risk: bool = False


class MacroRegime(BaseModel):
    """Composite macro regime classification."""
    rate_regime: str = "neutral"  # accommodative, tightening, transitioning
    credit_regime: str = "neutral"  # risk-on, risk-off, stress
    composite_label: str = "neutral"  # bullish_macro, bearish_macro, neutral_macro
    fed_funds_rate: Optional[float] = None
    hy_oas: Optional[float] = None  # High-yield option-adjusted spread
    yield_curve_spread: Optional[float] = None  # 3m-10y spread
    vix: Optional[float] = None
    context_string: str = ""


class DataQualityReport(BaseModel):
    """Tracks data completeness for each ticker."""
    ticker: str
    fields_requested: int = 0
    fields_received: int = 0
    fields_missing: List[str] = Field(default_factory=list)
    quality_score: float = 1.0  # 0.0 to 1.0
    warnings: List[str] = Field(default_factory=list)


class Tier0Output(BaseModel):
    ticker: str
    as_of: date
    solvency: Optional[SolvencyMetrics] = None
    efficiency: Optional[EfficiencyMetrics] = None
    profitability: Optional[ProfitabilityMetrics] = None
    investor_behavior: Optional[InvestorBehavior] = None
    technical: Optional[Technicals] = None
    peer_dynamics: Optional[PeerDynamics] = None
    normalized_metrics: Optional[NormalizedMetrics] = None
    factor_exposure: Optional[FactorExposureReport] = None
    options_signals: Optional[OptionsSignals] = None
    macro_regime: Optional[MacroRegime] = None
    data_quality: Optional[DataQualityReport] = None
