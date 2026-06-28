import logging
from typing import Optional
from pipeline.schemas.tier0 import InvestorBehavior
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)


def get_investor_behavior(ticker_symbol: str) -> Optional[InvestorBehavior]:
    """
    Computes investor behavior signals using the data vendor abstraction.
    Returns None if critical data is unavailable.
    """
    try:
        info = vendor.get_info(ticker_symbol)
        insider_txns = vendor.get_insider_transactions(ticker_symbol)

        short_interest = None
        if info is not None:
            raw_si = info.get('shortPercentOfFloat')
            if raw_si is not None:
                short_interest = float(raw_si) * 100

        buys = 0
        sells = 0
        if insider_txns is not None and not insider_txns.empty:
            for _, row in insider_txns.iterrows():
                shares = row.get('Shares', 0)
                if shares is not None:
                    if shares > 0:
                        buys += 1
                    elif shares < 0:
                        sells += 1

        return InvestorBehavior(
            institutional_delta_pct=None,
            insider_buys_90d=buys,
            insider_sells_90d=sells,
            short_interest_delta_pct=short_interest,
        )
    except Exception as e:
        logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=investor_behavior | reason=computation_error | detail={e}")
        return None
