import pandas as pd
import logging
from typing import Optional
from pipeline.schemas.tier0 import EfficiencyMetrics
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)


def get_efficiency_metrics(ticker_symbol: str) -> Optional[EfficiencyMetrics]:
    """
    Computes efficiency & turnover metrics using the data vendor abstraction.
    Returns None if critical data is unavailable.
    """
    financials_data = vendor.get_financials(ticker_symbol, period="quarterly")

    if financials_data is None:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=efficiency | reason=no_financial_data")
        return None

    balance_sheet = financials_data["balance_sheet"]
    financials = financials_data["financials"]

    if balance_sheet is None or balance_sheet.empty or financials is None or financials.empty:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=efficiency | reason=empty_statements")
        return None

    try:
        def safe_get(df: pd.DataFrame, row_names: list, default=None) -> Optional[float]:
            if df is not None and not df.empty:
                for name in row_names:
                    if name in df.index:
                        val = df.loc[name]
                        if isinstance(val, pd.Series):
                            val = val.iloc[0]
                        return float(val) if pd.notna(val) else default
            return default

        def safe_divide(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
            if numerator is None or denominator is None or denominator == 0:
                return None
            return numerator / denominator

        revenue = safe_get(financials, ["Total Revenue", "Revenues", "Operating Revenue"])
        cogs = safe_get(financials, ["Cost Of Revenue", "Reconciled Cost Of Revenue"])

        inventory = safe_get(balance_sheet, ["Inventory"])
        receivables = safe_get(balance_sheet, ["Accounts Receivable", "Receivables"])
        payables = safe_get(balance_sheet, ["Accounts Payable", "Payables"])

        inventory_turnover = safe_divide(cogs, inventory)
        receivables_turnover = safe_divide(revenue, receivables)
        payables_turnover = safe_divide(cogs, payables)

        # DSO (Days Sales Outstanding) = (Receivables / Revenue) * 90 days (since quarterly)
        dso = None
        if receivables is not None and revenue is not None and revenue != 0:
            dso = (receivables / revenue) * 90

        return EfficiencyMetrics(
            inventory_turnover=inventory_turnover,
            receivables_turnover=receivables_turnover,
            payables_turnover=payables_turnover,
            dso=dso,
        )
    except Exception as e:
        logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=efficiency | reason=computation_error | detail={e}")
        return None
