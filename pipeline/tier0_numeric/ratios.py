import yfinance as yf
import pandas as pd
from typing import Optional
from pipeline.schemas.tier0 import SolvencyMetrics

def get_solvency_metrics(ticker_symbol: str) -> SolvencyMetrics:
    ticker = yf.Ticker(ticker_symbol)
    balance_sheet = ticker.quarterly_balance_sheet
    financials = ticker.quarterly_financials
    cash_flow = ticker.quarterly_cash_flow
    
    def empty_metrics():
        return SolvencyMetrics(
            current_ratio=0.0, quick_ratio=0.0, cash_ratio=0.0, op_cash_flow_ratio=0.0, 
            working_cap=0.0, debt_equity=0.0, debt_ratio=0.0, equity_ratio=0.0, 
            debt_capital=0.0, interest_coverage=0.0, fixed_charge_coverage=0.0, 
            cash_flow_debt=0.0, trend_8q=[]
        )

    if balance_sheet is None or balance_sheet.empty:
        return empty_metrics()
    
    try:
        def safe_get(df, row_name, default=0.0):
            if df is not None and not df.empty and row_name in df.index:
                val = df.loc[row_name].iloc[0]
                return float(val) if pd.notna(val) else default
            return default

        current_assets = safe_get(balance_sheet, "Current Assets", 0)
        current_liabilities = safe_get(balance_sheet, "Current Liabilities", 1)
        inventory = safe_get(balance_sheet, "Inventory", 0)
        cash_and_equiv = safe_get(balance_sheet, "Cash And Cash Equivalents", 0)
        total_assets = safe_get(balance_sheet, "Total Assets", 1)
        total_liabilities = safe_get(balance_sheet, "Total Liabilities", 0)
        total_debt = safe_get(balance_sheet, "Total Debt", 0)
        total_equity = safe_get(balance_sheet, "Stockholders Equity", 1)
        
        ebit = safe_get(financials, "EBIT", 0)
        interest_expense = abs(safe_get(financials, "Interest Expense", 1))
        
        op_cash_flow = safe_get(cash_flow, "Operating Cash Flow", 0)
        
        # Calculations
        current_ratio = current_assets / current_liabilities if current_liabilities != 0 else 0.0
        quick_ratio = (current_assets - inventory) / current_liabilities if current_liabilities != 0 else 0.0
        cash_ratio = cash_and_equiv / current_liabilities if current_liabilities != 0 else 0.0
        op_cash_flow_ratio = op_cash_flow / current_liabilities if current_liabilities != 0 else 0.0
        working_cap = current_assets - current_liabilities
        
        debt_equity = total_debt / total_equity if total_equity != 0 else 0.0
        debt_ratio = total_debt / total_assets if total_assets != 0 else 0.0
        equity_ratio = total_equity / total_assets if total_assets != 0 else 0.0
        debt_capital = total_debt / (total_debt + total_equity) if (total_debt + total_equity) != 0 else 0.0
        
        interest_coverage = ebit / interest_expense if interest_expense != 0 else 0.0
        # Simplistic fixed charge coverage proxy (assuming fixed charges ~ interest expense)
        fixed_charge_coverage = ebit / interest_expense if interest_expense != 0 else 0.0
        cash_flow_debt = op_cash_flow / total_debt if total_debt != 0 else 0.0
        
        trend_8q = []
        if "Current Assets" in balance_sheet.index and "Current Liabilities" in balance_sheet.index:
            ca_trend = balance_sheet.loc["Current Assets"].head(8)
            cl_trend = balance_sheet.loc["Current Liabilities"].head(8)
            for ca, cl in zip(ca_trend, cl_trend):
                if pd.notna(ca) and pd.notna(cl) and cl != 0:
                    trend_8q.append(float(ca / cl))
                else:
                    trend_8q.append(0.0)
                    
        return SolvencyMetrics(
            current_ratio=float(current_ratio),
            quick_ratio=float(quick_ratio),
            cash_ratio=float(cash_ratio),
            op_cash_flow_ratio=float(op_cash_flow_ratio),
            working_cap=float(working_cap),
            debt_equity=float(debt_equity),
            debt_ratio=float(debt_ratio),
            equity_ratio=float(equity_ratio),
            debt_capital=float(debt_capital),
            interest_coverage=float(interest_coverage),
            fixed_charge_coverage=float(fixed_charge_coverage),
            cash_flow_debt=float(cash_flow_debt),
            trend_8q=trend_8q[::-1]
        )
    except Exception as e:
        print(f"Error computing solvency for {ticker_symbol}: {e}")
        return empty_metrics()
