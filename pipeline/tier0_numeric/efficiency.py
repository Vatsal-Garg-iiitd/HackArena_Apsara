import yfinance as yf
import pandas as pd
from pipeline.schemas.tier0 import EfficiencyMetrics

def get_efficiency_metrics(ticker_symbol: str) -> EfficiencyMetrics:
    ticker = yf.Ticker(ticker_symbol)
    balance_sheet = ticker.quarterly_balance_sheet
    financials = ticker.quarterly_financials
    
    def empty_metrics():
        return EfficiencyMetrics(
            inventory_turnover=0.0, receivables_turnover=0.0, payables_turnover=0.0, dso=0.0
        )
        
    if balance_sheet is None or balance_sheet.empty or financials is None or financials.empty:
        return empty_metrics()
        
    try:
        def safe_get(df, row_name, default=0.0):
            if df is not None and not df.empty and row_name in df.index:
                val = df.loc[row_name].iloc[0]
                return float(val) if pd.notna(val) else default
            return default

        revenue = safe_get(financials, "Total Revenue", 0)
        cogs = safe_get(financials, "Cost Of Revenue", 0)
        
        inventory = safe_get(balance_sheet, "Inventory", 1)
        receivables = safe_get(balance_sheet, "Accounts Receivable", 1)
        payables = safe_get(balance_sheet, "Accounts Payable", 1)
        
        # In a real app we'd average over periods, here we just use the latest quarter
        inventory_turnover = cogs / inventory if inventory != 0 else 0.0
        receivables_turnover = revenue / receivables if receivables != 0 else 0.0
        
        # Use COGS or operating expenses as proxy for purchases
        payables_turnover = cogs / payables if payables != 0 else 0.0
        
        # DSO (Days Sales Outstanding) = (Receivables / Revenue) * 90 days (since quarterly)
        dso = (receivables / revenue) * 90 if revenue != 0 else 0.0
        
        return EfficiencyMetrics(
            inventory_turnover=float(inventory_turnover),
            receivables_turnover=float(receivables_turnover),
            payables_turnover=float(payables_turnover),
            dso=float(dso)
        )
    except Exception as e:
        print(f"Error computing efficiency for {ticker_symbol}: {e}")
        return empty_metrics()
