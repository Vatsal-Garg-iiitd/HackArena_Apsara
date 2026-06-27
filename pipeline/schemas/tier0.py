from pydantic import BaseModel
from typing import List, Optional
from datetime import date

class SolvencyMetrics(BaseModel):
    current_ratio: float
    quick_ratio: float
    cash_ratio: float
    op_cash_flow_ratio: float
    working_cap: float
    debt_equity: float
    debt_ratio: float
    equity_ratio: float
    debt_capital: float
    interest_coverage: float
    fixed_charge_coverage: float
    cash_flow_debt: float
    trend_8q: List[float] # Assuming trend of current ratio

class EfficiencyMetrics(BaseModel):
    inventory_turnover: float
    receivables_turnover: float
    payables_turnover: float
    dso: float

class ProfitabilityMetrics(BaseModel):
    gross_margin: float
    operating_margin: float
    net_margin: float
    roa: float
    roe: float
    roce: float
    eps: float
    roi: float

class InvestorBehavior(BaseModel):
    institutional_delta_pct: float
    insider_buys_90d: int
    insider_sells_90d: int
    short_interest_delta_pct: float

class Technicals(BaseModel):
    rsi_14: float
    macd_signal: str
    volatility_60d: float
    sharpe_60d: float
    max_drawdown_60d: float

class PeerDynamics(BaseModel):
    peer_tickers: List[str]
    relative_sharpe: float
    relative_volatility: float
    relative_drawdown: float

class NormalizedMetrics(BaseModel):
    current_ratio_vs_peers: float
    debt_equity_vs_peers: float
    gross_margin_vs_peers: float
    roe_vs_peers: float

class Tier0Output(BaseModel):
    ticker: str
    as_of: date
    solvency: SolvencyMetrics
    efficiency: EfficiencyMetrics
    profitability: ProfitabilityMetrics
    investor_behavior: InvestorBehavior
    technical: Technicals
    peer_dynamics: PeerDynamics
    normalized_metrics: Optional[NormalizedMetrics] = None
