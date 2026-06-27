import yfinance as yf
from pipeline.schemas.tier0 import InvestorBehavior

def get_investor_behavior(ticker_symbol: str) -> InvestorBehavior:
    # In a fully integrated system with OpenBB, this would fetch real 13F and insider trades.
    # We will use yfinance fallbacks where possible or mock values if data is missing.
    ticker = yf.Ticker(ticker_symbol)
    
    try:
        # yfinance often returns short interest in the 'info' dict
        info = ticker.info
        short_interest = info.get('shortPercentOfFloat', 0.0) * 100
        
        # We don't easily get 90-day insider buys/sells from yfinance without parsing insider_transactions
        # This is a stubbed implementation to be augmented with OpenBB/EDGAR later.
        insider_transactions = ticker.insider_transactions
        buys = 0
        sells = 0
        if insider_transactions is not None and not insider_transactions.empty:
            # Simplistic parsing if data exists
            for _, row in insider_transactions.iterrows():
                # Not robust, but gives a proxy
                shares = row.get('Shares', 0)
                if shares > 0:
                    buys += 1
                elif shares < 0:
                    sells += 1
                    
        return InvestorBehavior(
            institutional_delta_pct=0.0, # Placeholder
            insider_buys_90d=buys,
            insider_sells_90d=sells,
            short_interest_delta_pct=short_interest
        )
    except Exception as e:
        print(f"Error computing investor behavior for {ticker_symbol}: {e}")
        return InvestorBehavior(
            institutional_delta_pct=0.0,
            insider_buys_90d=0,
            insider_sells_90d=0,
            short_interest_delta_pct=0.0
        )
