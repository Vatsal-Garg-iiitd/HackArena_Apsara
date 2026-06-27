"""
Options market signal extraction.
Computes forward-looking signals from options chain data:
IV Rank, put-call ratios, skew, term structure, event risk detection.
"""

import logging
import numpy as np
import pandas as pd
from typing import Optional
from pipeline.schemas.tier0 import OptionsSignals
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)


def compute_options_signals(ticker_symbol: str) -> Optional[OptionsSignals]:
    """
    Extract options-derived forward-looking signals.
    Uses the data vendor's options chain endpoint.
    """
    chain_data = vendor.get_options_chain(ticker_symbol)

    if chain_data is None:
        logger.info(f"No options data available for {ticker_symbol}")
        return None

    try:
        expirations = chain_data.get("expirations", [])
        chains = chain_data.get("chains", {})

        if not expirations or not chains:
            return None

        # Aggregate across available expirations
        total_call_volume = 0
        total_put_volume = 0
        total_call_oi = 0
        total_put_oi = 0
        iv_values = []

        for exp in expirations:
            exp_chain = chains.get(exp, {})
            calls = exp_chain.get("calls")
            puts = exp_chain.get("puts")

            if calls is not None and not calls.empty:
                if "volume" in calls.columns:
                    total_call_volume += calls["volume"].sum()
                if "openInterest" in calls.columns:
                    total_call_oi += calls["openInterest"].sum()
                if "impliedVolatility" in calls.columns:
                    iv_values.extend(calls["impliedVolatility"].dropna().tolist())

            if puts is not None and not puts.empty:
                if "volume" in puts.columns:
                    total_put_volume += puts["volume"].sum()
                if "openInterest" in puts.columns:
                    total_put_oi += puts["openInterest"].sum()
                if "impliedVolatility" in puts.columns:
                    iv_values.extend(puts["impliedVolatility"].dropna().tolist())

        # Put-call ratios
        pc_ratio_volume = total_put_volume / total_call_volume if total_call_volume > 0 else None
        pc_ratio_oi = total_put_oi / total_call_oi if total_call_oi > 0 else None

        # IV at the money (use median IV as proxy)
        iv_atm = float(np.median(iv_values)) if iv_values else None

        # IV Rank (would need historical IV data for true 52-week rank)
        # For now, use a percentile within current chain as a proxy
        iv_rank = None
        if iv_values and iv_atm is not None:
            iv_rank = float(np.searchsorted(sorted(iv_values), iv_atm) / len(iv_values) * 100)

        # Term structure: compare near-term vs far-term IV
        term_structure = "normal"
        if len(expirations) >= 2:
            near_exp = expirations[0]
            far_exp = expirations[-1]
            near_chain = chains.get(near_exp, {})
            far_chain = chains.get(far_exp, {})

            near_calls = near_chain.get("calls")
            far_calls = far_chain.get("calls")

            if (near_calls is not None and not near_calls.empty and
                    "impliedVolatility" in near_calls.columns and
                    far_calls is not None and not far_calls.empty and
                    "impliedVolatility" in far_calls.columns):
                near_iv = near_calls["impliedVolatility"].median()
                far_iv = far_calls["impliedVolatility"].median()
                if pd.notna(near_iv) and pd.notna(far_iv):
                    if near_iv > far_iv * 1.1:
                        term_structure = "backwardation"  # Near-term event risk
                    elif near_iv < far_iv * 0.9:
                        term_structure = "normal"
                    else:
                        term_structure = "flat"

        # Near-term event risk flag
        near_term_event_risk = term_structure == "backwardation"

        return OptionsSignals(
            iv_rank=round(iv_rank, 2) if iv_rank is not None else None,
            put_call_ratio_volume=round(pc_ratio_volume, 4) if pc_ratio_volume is not None else None,
            put_call_ratio_oi=round(pc_ratio_oi, 4) if pc_ratio_oi is not None else None,
            put_skew=None,  # Requires specific delta computation
            term_structure=term_structure,
            iv_at_money=round(iv_atm, 4) if iv_atm is not None else None,
            near_term_event_risk=near_term_event_risk,
        )

    except Exception as e:
        logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=options | reason=computation_error | detail={e}")
        return None
