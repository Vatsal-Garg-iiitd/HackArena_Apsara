import pandas as pd
import logging
from typing import Optional
from pipeline.schemas.tier0 import ProfitabilityMetrics
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)


def get_profitability_metrics(ticker_symbol: str) -> Optional[ProfitabilityMetrics]:
    """
    Computes profitability metrics using the data vendor abstraction.
    Returns None if critical data is unavailable.
    """
    financials_data = vendor.get_financials(ticker_symbol, period="quarterly")

    if financials_data is None:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=profitability | reason=no_financial_data")
        return None

    balance_sheet = financials_data["balance_sheet"]
    financials = financials_data["financials"]

    if balance_sheet is None or balance_sheet.empty or financials is None or financials.empty:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=profitability | reason=empty_statements")
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
        gross_profit = safe_get(financials, ["Gross Profit"])
        operating_income = safe_get(financials, ["Operating Income", "Operating Income/Loss"])
        net_income = safe_get(financials, ["Net Income", "Net Income/Loss"])
        ebit = safe_get(financials, ["EBIT", "Operating Income/Loss", "Operating Income"])
        eps = safe_get(financials, ["Basic EPS", "Basic Earnings Per Share"])

        total_assets = safe_get(balance_sheet, ["Total Assets", "Assets"])
        total_equity = safe_get(balance_sheet, ["Stockholders Equity", "Equity", "Common Stock Equity"])
        total_debt = safe_get(balance_sheet, ["Total Debt", "Long-term Debt", "Long Term Debt"])
        current_liabilities = safe_get(balance_sheet, ["Current Liabilities"])

        capital_employed = None
        if total_assets is not None and current_liabilities is not None:
            capital_employed = total_assets - current_liabilities
            if capital_employed == 0:
                capital_employed = None

        gross_margin = safe_divide(gross_profit, revenue)
        operating_margin = safe_divide(operating_income, revenue)
        net_margin = safe_divide(net_income, revenue)

        roa = safe_divide(net_income, total_assets)
        roe = safe_divide(net_income, total_equity)
        roce = safe_divide(ebit, capital_employed)

        # Simple ROI proxy using net income over (debt + equity)
        invested_capital = None
        if total_debt is not None and total_equity is not None:
            invested_capital = total_debt + total_equity
        roi = safe_divide(net_income, invested_capital)

        return ProfitabilityMetrics(
            gross_margin=gross_margin,
            operating_margin=operating_margin,
            net_margin=net_margin,
            roa=roa,
            roe=roe,
            roce=roce,
            eps=eps,
            roi=roi,
        )
    except Exception as e:
        logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=profitability | reason=computation_error | detail={e}")
        return None
