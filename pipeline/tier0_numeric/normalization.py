import logging
import statistics
from typing import Optional
from pipeline.schemas.tier0 import NormalizedMetrics, SolvencyMetrics, ProfitabilityMetrics
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)


def get_normalized_metrics(
    ticker_symbol: str,
    base_solvency: Optional[SolvencyMetrics],
    base_profit: Optional[ProfitabilityMetrics],
    macro_context: Optional[str] = None,
) -> Optional[NormalizedMetrics]:
    """
    Computes peer-normalized metrics with macro regime context.
    Returns None if base metrics are unavailable.
    """
    if base_solvency is None or base_profit is None:
        return None

    from pipeline.tier0_numeric.peer_dynamics import _discover_peers
    from pipeline.tier0_numeric.ratios import get_solvency_metrics
    from pipeline.tier0_numeric.profitability import get_profitability_metrics

    peers = _discover_peers(ticker_symbol)

    if not peers:
        return NormalizedMetrics(
            macro_regime=macro_context,
        )

    try:
        peer_current_ratios = []
        peer_debt_equities = []
        peer_gross_margins = []
        peer_roes = []

        for peer in peers:
            solv = get_solvency_metrics(peer)
            prof = get_profitability_metrics(peer)

            if solv is not None and solv.current_ratio is not None:
                peer_current_ratios.append(solv.current_ratio)
            if solv is not None and solv.debt_equity is not None:
                peer_debt_equities.append(solv.debt_equity)
            if prof is not None and prof.gross_margin is not None:
                peer_gross_margins.append(prof.gross_margin)
            if prof is not None and prof.roe is not None:
                peer_roes.append(prof.roe)

        def safe_median_diff(base_val: Optional[float], peer_vals: list) -> Optional[float]:
            if base_val is None or not peer_vals:
                return None
            return round(base_val - statistics.median(peer_vals), 4)

        return NormalizedMetrics(
            current_ratio_vs_peers=safe_median_diff(base_solvency.current_ratio, peer_current_ratios),
            debt_equity_vs_peers=safe_median_diff(base_solvency.debt_equity, peer_debt_equities),
            gross_margin_vs_peers=safe_median_diff(base_profit.gross_margin, peer_gross_margins),
            roe_vs_peers=safe_median_diff(base_profit.roe, peer_roes),
            macro_regime=macro_context,
        )
    except Exception as e:
        logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=normalization | reason=computation_error | detail={e}")
        return NormalizedMetrics(macro_regime=macro_context)
