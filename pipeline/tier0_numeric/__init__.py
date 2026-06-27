"""
Tier 0 — Numeric Engine.
Computes all pure-code metrics with proper None-propagation.
Logs data quality failures and skips tickers with missing critical data.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from pipeline.schemas.tier0 import Tier0Output, DataQualityReport
from pipeline.infra.data_vendor import vendor
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
from .institutional_flow import compute_institutional_flow

logger = logging.getLogger(__name__)


def generate_tier0_output(
    ticker: str,
    macro=None,
    risk_free_rate: Optional[float] = None,
    mode: str = "deep",
) -> Optional[Tier0Output]:
    """
    Generate all Tier 0 numeric metrics for a ticker.
    Returns None if critical data is missing (never produces corrupted signals).
    """
    # Track data quality
    mode = mode.lower()
    include_peer_metrics = mode != "fast"
    include_extended_metrics = mode == "deep"
    fields_requested = 7 if include_peer_metrics else 5
    fields_received = 0
    fields_missing = []
    warnings = []

    # Shared data fetches. These are the dominant latency source, so fetch once
    # and pass the data into each metric calculator.
    financials_data = vendor.get_financials(ticker, period="quarterly")
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    hist = vendor.get_ohlcv(ticker, start=start_date, end=end_date)

    # Core metrics
    solvency = get_solvency_metrics(ticker, financials_data) if financials_data is not None else None
    if solvency is not None:
        fields_received += 1
    else:
        fields_missing.append("solvency")

    efficiency = get_efficiency_metrics(ticker, financials_data) if financials_data is not None else None
    if efficiency is not None:
        fields_received += 1
    else:
        fields_missing.append("efficiency")

    profitability = get_profitability_metrics(ticker, financials_data) if financials_data is not None else None
    if profitability is not None:
        fields_received += 1
    else:
        fields_missing.append("profitability")

    investor_behavior = get_investor_behavior(ticker)
    if investor_behavior is not None:
        fields_received += 1
    else:
        fields_missing.append("investor_behavior")

    technical = get_technicals(ticker, hist=hist, risk_free_rate=risk_free_rate) if hist is not None else None
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

    if macro is None:
        # Backward-compatible fallback for callers outside the orchestrator.
        try:
            macro = classify_macro_regime()
        except Exception as e:
            logger.warning(f"Macro regime classification failed: {e}")
            macro = None

    macro_context = macro.context_string if macro else None

    peer_dynamics = None
    normalized = None
    if include_peer_metrics:
        # Peer dynamics
        peer_dynamics = get_peer_dynamics(ticker, base_tech=technical, risk_free_rate=risk_free_rate)
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
    if include_extended_metrics:
        try:
            factor_exposure = compute_factor_exposure(ticker, hist=hist)
        except Exception as e:
            logger.warning(f"Factor exposure computation failed for {ticker}: {e}")
            warnings.append(f"factor_exposure: {e}")

    options_signals = None
    if include_extended_metrics:
        try:
            options_signals = compute_options_signals(ticker)
        except Exception as e:
            logger.warning(f"Options signals computation failed for {ticker}: {e}")
            warnings.append(f"options_signals: {e}")

    institutional_flow = None
    if include_extended_metrics:
        try:
            institutional_flow = compute_institutional_flow(ticker)
        except Exception as e:
            logger.warning(f"Institutional flow computation failed for {ticker}: {e}")
            warnings.append(f"institutional_flow: {e}")

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
        institutional_flow=institutional_flow,
        data_quality=data_quality,
    )
