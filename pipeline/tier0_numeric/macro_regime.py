"""
Macro Regime Classifier.
Pulls macro indicators from FRED and classifies the current environment
into discrete regime labels that modulate how signals are interpreted.
"""

import logging
from typing import Optional
import requests
from pipeline.schemas.tier0 import MacroRegime

logger = logging.getLogger(__name__)

# FRED demo key for low-volume use
FRED_API_KEY = "DEMO_KEY"


def _fetch_fred_series(series_id: str) -> Optional[float]:
    """Fetch the latest value of a FRED series."""
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            obs = data.get("observations", [])
            if obs:
                value = obs[0].get("value", ".")
                if value != ".":
                    return float(value)
    except Exception as e:
        logger.warning(f"Could not fetch FRED series {series_id}: {e}")
    return None


def classify_macro_regime() -> MacroRegime:
    """
    Classify current macro environment using FRED indicators:
    - Federal Funds Rate (FEDFUNDS)
    - ICE BofA HY OAS (BAMLH0A0HYM2) 
    - 3M-10Y Treasury Spread (T10Y3M)
    - VIX (VIXCLS)
    """
    # Fetch indicators
    fed_funds = _fetch_fred_series("FEDFUNDS")
    hy_oas = _fetch_fred_series("BAMLH0A0HYM2")
    yield_curve_spread = _fetch_fred_series("T10Y3M")
    vix = _fetch_fred_series("VIXCLS")

    # Rate regime classification
    rate_regime = "neutral"
    if fed_funds is not None:
        if fed_funds >= 4.0:
            rate_regime = "tightening"
        elif fed_funds <= 1.5:
            rate_regime = "accommodative"
        else:
            rate_regime = "transitioning"

    # Yield curve analysis
    if yield_curve_spread is not None and yield_curve_spread < 0:
        rate_regime = "tightening"  # Inversion overrides
    elif yield_curve_spread is not None and yield_curve_spread > 1.0:
        rate_regime = "accommodative"

    # Credit regime classification
    credit_regime = "neutral"
    if hy_oas is not None:
        if hy_oas >= 600:
            credit_regime = "stress"
        elif hy_oas >= 400:
            credit_regime = "risk-off"
        else:
            credit_regime = "risk-on"

    # Volatility regime
    vol_regime = "moderate"
    if vix is not None:
        if vix >= 25:
            vol_regime = "high"
        elif vix <= 15:
            vol_regime = "low"

    # Composite label
    bullish_score = 0
    bearish_score = 0

    if rate_regime == "accommodative":
        bullish_score += 1
    elif rate_regime == "tightening":
        bearish_score += 1

    if credit_regime == "risk-on":
        bullish_score += 1
    elif credit_regime in ("risk-off", "stress"):
        bearish_score += 1

    if vol_regime == "low":
        bullish_score += 1
    elif vol_regime == "high":
        bearish_score += 1

    if bullish_score >= 2:
        composite = "bullish_macro"
    elif bearish_score >= 2:
        composite = "bearish_macro"
    else:
        composite = "neutral_macro"

    # Build context string for LLM
    context_parts = []
    context_parts.append(f"rate_environment={rate_regime}")
    if fed_funds is not None:
        context_parts.append(f"fed_funds={fed_funds:.2f}%")
    context_parts.append(f"credit_stress={'elevated' if credit_regime in ('risk-off', 'stress') else 'moderate' if credit_regime == 'neutral' else 'compressed'}")
    if hy_oas is not None:
        context_parts.append(f"hy_oas={hy_oas:.0f}bp")
    context_parts.append(f"volatility_regime={vol_regime}")
    if vix is not None:
        context_parts.append(f"vix={vix:.1f}")
    if yield_curve_spread is not None:
        context_parts.append(f"yield_curve_spread={yield_curve_spread:.2f}%")

    context_string = f"Current macro regime: {composite}. " + ", ".join(context_parts)

    return MacroRegime(
        rate_regime=rate_regime,
        credit_regime=credit_regime,
        composite_label=composite,
        fed_funds_rate=fed_funds,
        hy_oas=hy_oas,
        yield_curve_spread=yield_curve_spread,
        vix=vix,
        context_string=context_string,
    )
