import yfinance as yf
import pandas as pd
from pipeline.schemas.tier0 import ProfitabilityMetrics

def get_profitability_metrics(ticker_symbol: str) -> ProfitabilityMetrics:
    ticker = yf.Ticker(ticker_symbol)
    balance_sheet = ticker.quarterly_balance_sheet
    financials = ticker.quarterly_financials
    
    def empty_metrics():
        return ProfitabilityMetrics(
            gross_margin=0.0, operating_margin=0.0, net_margin=0.0, 
            roa=0.0, roe=0.0, roce=0.0, eps=0.0, roi=0.0
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
        gross_profit = safe_get(financials, "Gross Profit", 0)
        operating_income = safe_get(financials, "Operating Income", 0)
        net_income = safe_get(financials, "Net Income", 0)
        ebit = safe_get(financials, "EBIT", 0)
        eps = safe_get(financials, "Basic EPS", 0)
        
        total_assets = safe_get(balance_sheet, "Total Assets", 1)
        total_equity = safe_get(balance_sheet, "Stockholders Equity", 1)
        total_debt = safe_get(balance_sheet, "Total Debt", 0)
        capital_employed = total_assets - safe_get(balance_sheet, "Current Liabilities", 0)
        if capital_employed == 0:
            capital_employed = 1
            
        gross_margin = gross_profit / revenue if revenue != 0 else 0.0
        operating_margin = operating_income / revenue if revenue != 0 else 0.0
        net_margin = net_income / revenue if revenue != 0 else 0.0
        
        roa = net_income / total_assets if total_assets != 0 else 0.0
        roe = net_income / total_equity if total_equity != 0 else 0.0
        roce = ebit / capital_employed
        
        # Simple ROI proxy using net income over (debt + equity)
        invested_capital = total_debt + total_equity
        roi = net_income / invested_capital if invested_capital != 0 else 0.0
        
        return ProfitabilityMetrics(
            gross_margin=float(gross_margin),
            operating_margin=float(operating_margin),
            net_margin=float(net_margin),
            roa=float(roa),
            roe=float(roe),
            roce=float(roce),
            eps=float(eps),
            roi=float(roi)
        )
    except Exception as e:
        print(f"Error computing profitability for {ticker_symbol}: {e}")
        return empty_metrics()
