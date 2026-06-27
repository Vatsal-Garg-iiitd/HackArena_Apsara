import pandas as pd
import logging
from typing import Optional, Dict
from pipeline.schemas.tier0 import SolvencyMetrics
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)


def get_solvency_metrics(
    ticker_symbol: str,
    financials_data: Optional[Dict[str, pd.DataFrame]] = None,
) -> Optional[SolvencyMetrics]:
    """
    Computes solvency & liquidity metrics using the data vendor abstraction.
    Returns None if critical data is unavailable — never returns 0.0 fallbacks.
    """
    if financials_data is None:
        financials_data = vendor.get_financials(ticker_symbol, period="quarterly")

    if financials_data is None:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=solvency | reason=no_financial_data")
        return None

    balance_sheet = financials_data["balance_sheet"]
    financials = financials_data["financials"]
    cash_flow = financials_data["cash_flow"]

    if balance_sheet is None or balance_sheet.empty:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=solvency | reason=empty_balance_sheet")
        return None

    try:
        def safe_get(df: pd.DataFrame, row_names: list, default=None) -> Optional[float]:
            """Returns first valid value from list of concept aliases."""
            if df is not None and not df.empty:
                for name in row_names:
                    if name in df.index:
                        val = df.loc[name]
                        if isinstance(val, pd.Series):
                            val = val.iloc[0]
                        return float(val) if pd.notna(val) else default
            return default

        current_assets = safe_get(balance_sheet, ["Current Assets"])
        current_liabilities = safe_get(balance_sheet, ["Current Liabilities"])
        inventory = safe_get(balance_sheet, ["Inventory"])
        cash_and_equiv = safe_get(balance_sheet, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash"])
        total_assets = safe_get(balance_sheet, ["Total Assets", "Assets"])
        total_liabilities = safe_get(balance_sheet, ["Total Liabilities", "Liabilities"])
        total_debt = safe_get(balance_sheet, ["Total Debt", "Long-term Debt", "Long Term Debt"])
        total_equity = safe_get(balance_sheet, ["Stockholders Equity", "Equity", "Common Stock Equity"])

        ebit = safe_get(financials, ["EBIT", "Operating Income/Loss", "Operating Income"])
        interest_expense_raw = safe_get(financials, ["Interest Expense", "Interest Expense/Benefit"])
        interest_expense = abs(interest_expense_raw) if interest_expense_raw is not None else None

        op_cash_flow = safe_get(cash_flow, ["Operating Cash Flow", "Net Cash Flow From Operating Activities", "Net Cash Flow From Operating Activities, Continuing"])

        # Critical fields check — if we can't compute the basic ratios, abort
        if current_assets is None or current_liabilities is None:
            logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=current_ratio | reason=missing_ca_or_cl")
            return None

        # Calculations — use None instead of 0.0 when denominator is missing/zero
        def safe_divide(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
            if numerator is None or denominator is None or denominator == 0:
                return None
            return numerator / denominator

        current_ratio = safe_divide(current_assets, current_liabilities)
        quick_ratio = safe_divide(
            (current_assets - inventory) if inventory is not None else current_assets,
            current_liabilities
        )
        cash_ratio = safe_divide(cash_and_equiv, current_liabilities)
        op_cash_flow_ratio = safe_divide(op_cash_flow, current_liabilities)
        working_cap = current_assets - current_liabilities if current_liabilities else None

        debt_equity = safe_divide(total_debt, total_equity)
        debt_ratio = safe_divide(total_debt, total_assets)
        equity_ratio = safe_divide(total_equity, total_assets)
        debt_capital = safe_divide(
            total_debt,
            (total_debt + total_equity) if total_debt is not None and total_equity is not None else None
        )

        interest_coverage = safe_divide(ebit, interest_expense)
        fixed_charge_coverage = safe_divide(ebit, interest_expense)
        cash_flow_debt = safe_divide(op_cash_flow, total_debt)

        # Trend: 8-quarter current ratio
        trend_8q = []
        if "Current Assets" in balance_sheet.index and "Current Liabilities" in balance_sheet.index:
            ca_trend = balance_sheet.loc["Current Assets"].head(8)
            cl_trend = balance_sheet.loc["Current Liabilities"].head(8)
            for ca, cl in zip(ca_trend, cl_trend):
                if pd.notna(ca) and pd.notna(cl) and cl != 0:
                    trend_8q.append(round(float(ca / cl), 4))

        return SolvencyMetrics(
            current_ratio=current_ratio,
            quick_ratio=quick_ratio,
            cash_ratio=cash_ratio,
            op_cash_flow_ratio=op_cash_flow_ratio,
            working_cap=working_cap,
            debt_equity=debt_equity,
            debt_ratio=debt_ratio,
            equity_ratio=equity_ratio,
            debt_capital=debt_capital,
            interest_coverage=interest_coverage,
            fixed_charge_coverage=fixed_charge_coverage,
            cash_flow_debt=cash_flow_debt,
            trend_8q=trend_8q[::-1]
        )
    except Exception as e:
        logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=solvency | reason=computation_error | detail={e}")
        return None
