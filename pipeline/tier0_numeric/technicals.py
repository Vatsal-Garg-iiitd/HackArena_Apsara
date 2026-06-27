import yfinance as yf
import pandas as pd
import numpy as np
from pipeline.schemas.tier0 import Technicals

def compute_rsi(data: pd.Series, window: int = 14) -> float:
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

def compute_macd(data: pd.Series) -> str:
    exp1 = data.ewm(span=12, adjust=False).mean()
    exp2 = data.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    
    if macd.iloc[-1] > signal.iloc[-1]:
        return "bullish"
    else:
        return "bearish"

def get_technicals(ticker_symbol: str) -> Technicals:
    ticker = yf.Ticker(ticker_symbol)
    # Get 60 days of data for volatility, sharpe, max drawdown
    hist = ticker.history(period="3mo")
    
    if hist.empty:
        return Technicals(rsi_14=50.0, macd_signal="neutral", volatility_60d=0.0, sharpe_60d=0.0, max_drawdown_60d=0.0)
        
    try:
        close = hist['Close']
        returns = close.pct_change().dropna()
        
        rsi = compute_rsi(close)
        macd_signal = compute_macd(close)
        
        volatility = returns.std() * np.sqrt(252) # Annualized volatility
        
        # Risk free rate approx 4%
        rf_daily = 0.04 / 252
        excess_returns = returns - rf_daily
        sharpe = np.sqrt(252) * excess_returns.mean() / returns.std() if returns.std() != 0 else 0
        
        cumulative = (1 + returns).cumprod()
        peak = cumulative.expanding(min_periods=1).max()
        drawdown = (cumulative - peak) / peak
        max_drawdown = drawdown.min()
        
        return Technicals(
            rsi_14=float(rsi),
            macd_signal=macd_signal,
            volatility_60d=float(volatility),
            sharpe_60d=float(sharpe),
            max_drawdown_60d=float(max_drawdown)
        )
    except Exception as e:
        print(f"Error computing technicals for {ticker_symbol}: {e}")
        return Technicals(rsi_14=50.0, macd_signal="neutral", volatility_60d=0.0, sharpe_60d=0.0, max_drawdown_60d=0.0)
