"""
Tier 0 — Numeric Engine.
Computes all pure-code metrics with proper None-propagation.
Logs data quality failures and skips tickers with missing critical data.
"""

import logging
from datetime import date
from typing import Optional
from pipeline.schemas.tier0 import Tier0Output, DataQualityReport
from .ratios import get_solvency_metrics
from .efficiency import get_efficiency_metrics
from .profitability import get_profitability_metrics
from .investor_signals import get_investor_behavior
from .technicals import get_technicals
from .peer_dynamics import get_peer_dynamics
from .normalization import get_normalized_metrics
from .factor_model import compute_factor_exposure
from .options_signals import compute_options_signals
from .macro_regime import classify_macro_regime
logger = logging.getLogger(__name__)


def generate_tier0_output(ticker: str) -> Optional[Tier0Output]:
    """
    Generate all Tier 0 numeric metrics for a ticker.
    Returns None if critical data is missing (never produces corrupted signals).
    """
    # Track data quality
    fields_requested = 7  # solvency, efficiency, profitability, investor, technical, peer, normalized
    fields_received = 0
    fields_missing = []
    warnings = []

    # Core metrics
    solvency = get_solvency_metrics(ticker)
    if solvency is not None:
        fields_received += 1
    else:
        fields_missing.append("solvency")

    efficiency = get_efficiency_metrics(ticker)
    if efficiency is not None:
        fields_received += 1
    else:
        fields_missing.append("efficiency")

    profitability = get_profitability_metrics(ticker)
    if profitability is not None:
        fields_received += 1
    else:
        fields_missing.append("profitability")

    investor_behavior = get_investor_behavior(ticker)
    if investor_behavior is not None:
        fields_received += 1
    else:
        fields_missing.append("investor_behavior")

    technical = get_technicals(ticker)
    if technical is not None:
        fields_received += 1
    else:
        fields_missing.append("technical")

    # Critical field check: abort if solvency AND technicals are both missing
    if solvency is None and technical is None:
        logger.error(
            f"DATA_QUALITY_FAILURE | ticker={ticker} | reason=critical_fields_missing | "
            f"missing={fields_missing} | Aborting ticker."
        )
        return None

    # Macro regime (runs once per day, shared across tickers)
    try:
        macro = classify_macro_regime()
        macro_context = macro.context_string
    except Exception as e:
        logger.warning(f"Macro regime classification failed: {e}")
        macro = None
        macro_context = None

    # Peer dynamics
    peer_dynamics = get_peer_dynamics(ticker)
    if peer_dynamics is not None:
        fields_received += 1
    else:
        fields_missing.append("peer_dynamics")

    # Normalized metrics
    normalized = get_normalized_metrics(ticker, solvency, profitability, macro_context)
    if normalized is not None:
        fields_received += 1
    else:
        fields_missing.append("normalized_metrics")

    # Extended metrics (non-critical — failures don't abort the ticker)
    factor_exposure = None
    try:
        factor_exposure = compute_factor_exposure(ticker)
    except Exception as e:
        logger.warning(f"Factor exposure computation failed for {ticker}: {e}")
        warnings.append(f"factor_exposure: {e}")

    options_signals = None
    try:
        options_signals = compute_options_signals(ticker)
    except Exception as e:
        logger.warning(f"Options signals computation failed for {ticker}: {e}")
        warnings.append(f"options_signals: {e}")

    # Data quality report
    quality_score = fields_received / fields_requested if fields_requested > 0 else 0.0
    data_quality = DataQualityReport(
        ticker=ticker,
        fields_requested=fields_requested,
        fields_received=fields_received,
        fields_missing=fields_missing,
        quality_score=round(quality_score, 4),
        warnings=warnings,
    )

    if quality_score < 0.5:
        logger.warning(
            f"LOW_DATA_QUALITY | ticker={ticker} | score={quality_score:.2f} | "
            f"missing={fields_missing}"
        )

    return Tier0Output(
        ticker=ticker,
        as_of=date.today(),
        solvency=solvency,
        efficiency=efficiency,
        profitability=profitability,
        investor_behavior=investor_behavior,
        technical=technical,
        peer_dynamics=peer_dynamics,
        normalized_metrics=normalized,
        factor_exposure=factor_exposure,
        options_signals=options_signals,
        macro_regime=macro,
        data_quality=data_quality,
    )
