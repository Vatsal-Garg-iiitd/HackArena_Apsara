from typing import List
import statistics
from pipeline.schemas.tier0 import NormalizedMetrics, SolvencyMetrics, ProfitabilityMetrics
from pipeline.tier0_numeric.peer_dynamics import MOCK_PEERS
from pipeline.tier0_numeric.ratios import get_solvency_metrics
from pipeline.tier0_numeric.profitability import get_profitability_metrics

def get_normalized_metrics(ticker_symbol: str, base_solvency: SolvencyMetrics, base_profit: ProfitabilityMetrics) -> NormalizedMetrics:
    peers = MOCK_PEERS.get(ticker_symbol, [])
    
    if not peers:
        return NormalizedMetrics(
            current_ratio_vs_peers=0.0,
            debt_equity_vs_peers=0.0,
            gross_margin_vs_peers=0.0,
            roe_vs_peers=0.0
        )
        
    try:
        peer_current_ratios = []
        peer_debt_equities = []
        peer_gross_margins = []
        peer_roes = []
        
        for peer in peers:
            solv = get_solvency_metrics(peer)
            prof = get_profitability_metrics(peer)
            peer_current_ratios.append(solv.current_ratio)
            peer_debt_equities.append(solv.debt_equity)
            peer_gross_margins.append(prof.gross_margin)
            peer_roes.append(prof.roe)
            
        def safe_median(lst: List[float]) -> float:
            return statistics.median(lst) if lst else 0.0
            
        return NormalizedMetrics(
            current_ratio_vs_peers=base_solvency.current_ratio - safe_median(peer_current_ratios),
            debt_equity_vs_peers=base_solvency.debt_equity - safe_median(peer_debt_equities),
            gross_margin_vs_peers=base_profit.gross_margin - safe_median(peer_gross_margins),
            roe_vs_peers=base_profit.roe - safe_median(peer_roes)
        )
    except Exception as e:
        print(f"Error computing normalized metrics for {ticker_symbol}: {e}")
        return NormalizedMetrics(
            current_ratio_vs_peers=0.0,
            debt_equity_vs_peers=0.0,
            gross_margin_vs_peers=0.0,
            roe_vs_peers=0.0
        )
