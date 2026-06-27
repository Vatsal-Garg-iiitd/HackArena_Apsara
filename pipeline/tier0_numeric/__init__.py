from datetime import date
from pipeline.schemas.tier0 import Tier0Output
from .ratios import get_solvency_metrics
from .efficiency import get_efficiency_metrics
from .profitability import get_profitability_metrics
from .investor_signals import get_investor_behavior
from .technicals import get_technicals
from .peer_dynamics import get_peer_dynamics
from .normalization import get_normalized_metrics

def generate_tier0_output(ticker: str) -> Tier0Output:
    solvency = get_solvency_metrics(ticker)
    efficiency = get_efficiency_metrics(ticker)
    profitability = get_profitability_metrics(ticker)
    investor_behavior = get_investor_behavior(ticker)
    technical = get_technicals(ticker)
    peer_dynamics = get_peer_dynamics(ticker)
    normalized = get_normalized_metrics(ticker, solvency, profitability)
    
    return Tier0Output(
        ticker=ticker,
        as_of=date.today(),
        solvency=solvency,
        efficiency=efficiency,
        profitability=profitability,
        investor_behavior=investor_behavior,
        technical=technical,
        peer_dynamics=peer_dynamics,
        normalized_metrics=normalized
    )
