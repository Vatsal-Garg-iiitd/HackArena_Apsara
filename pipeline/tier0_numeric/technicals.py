import pandas as pd
import numpy as np
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional
from pipeline.schemas.tier0 import Technicals, RollingSharpe, MaxDrawdownDetail
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)


def _fetch_risk_free_rate() -> float:
    """
    Fetch the 3-month US Treasury Bill rate from FRED (series TB3MS).
    Falls back to a sensible default if FRED is unavailable.
    """
    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": "TB3MS",
            "api_key": "DEMO_KEY",  # FRED demo key for low-volume use
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            observations = data.get("observations", [])
            if observations:
                value = observations[0].get("value", ".")
                if value != ".":
                    return float(value) / 100.0  # Convert percentage to decimal
    except Exception as e:
        logger.warning(f"Could not fetch risk-free rate from FRED: {e}")

    # Fallback: use a reasonable estimate
    return 0.0425  # ~4.25% as of mid-2026


def compute_rsi(data: pd.Series, window: int = 14) -> Optional[float]:
    if len(data) < window + 1:
        return None
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    last_rsi = rsi.iloc[-1]
    return float(last_rsi) if not pd.isna(last_rsi) else None


def compute_macd(data: pd.Series) -> str:
    if len(data) < 26:
        return "neutral"
    exp1 = data.ewm(span=12, adjust=False).mean()
    exp2 = data.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()

    if macd.iloc[-1] > signal.iloc[-1]:
        return "bullish"
    else:
        return "bearish"


def compute_rolling_sharpe(returns: pd.Series, rf_daily: float, window: int = 252) -> Optional[RollingSharpe]:
    """
    Compute rolling Sharpe ratios over 252-day windows.
    Returns distribution stats instead of a single point estimate.
    """
    if len(returns) < window:
        # Not enough data for rolling — compute a single estimate
        excess = returns - rf_daily
        std = returns.std()
        if std == 0 or pd.isna(std):
            return None
        sharpe_val = float(np.sqrt(252) * excess.mean() / std)
        return RollingSharpe(
            current=sharpe_val,
            mean=sharpe_val,
            median=sharpe_val,
            std=0.0,
            min=sharpe_val,
            max=sharpe_val,
            window_count=1,
        )

    excess = returns - rf_daily
    rolling_mean = excess.rolling(window=window).mean()
    rolling_std = returns.rolling(window=window).std()

    # Avoid division by zero
    valid = rolling_std > 0
    rolling_sharpe = pd.Series(np.nan, index=returns.index)
    rolling_sharpe[valid] = np.sqrt(252) * rolling_mean[valid] / rolling_std[valid]
    rolling_sharpe = rolling_sharpe.dropna()

    if rolling_sharpe.empty:
        return None

    return RollingSharpe(
        current=float(rolling_sharpe.iloc[-1]),
        mean=float(rolling_sharpe.mean()),
        median=float(rolling_sharpe.median()),
        std=float(rolling_sharpe.std()),
        min=float(rolling_sharpe.min()),
        max=float(rolling_sharpe.max()),
        window_count=len(rolling_sharpe),
    )


def compute_max_drawdown(returns: pd.Series) -> Optional[MaxDrawdownDetail]:
    """
    Compute max drawdown over full period and per calendar year.
    Includes recovery time estimation.
    """
    if returns.empty:
        return None

    cumulative = (1 + returns).cumprod()
    peak = cumulative.expanding(min_periods=1).max()
    drawdown = (cumulative - peak) / peak

    full_period_dd = float(drawdown.min())

    # Recovery time: how many days from max drawdown back to peak
    recovery_days = None
    dd_min_idx = drawdown.idxmin()
    if dd_min_idx is not None:
        post_dd = cumulative.loc[dd_min_idx:]
        peak_at_dd = peak.loc[dd_min_idx]
        recovered = post_dd[post_dd >= peak_at_dd]
        if not recovered.empty:
            recovery_days = (recovered.index[0] - dd_min_idx).days

    # Per-year drawdown
    per_year = {}
    if hasattr(returns.index, 'year'):
        for year in returns.index.year.unique():
            year_returns = returns[returns.index.year == year]
            if len(year_returns) > 0:
                year_cum = (1 + year_returns).cumprod()
                year_peak = year_cum.expanding(min_periods=1).max()
                year_dd = (year_cum - year_peak) / year_peak
                per_year[str(year)] = float(year_dd.min())

    return MaxDrawdownDetail(
        full_period=full_period_dd,
        full_period_recovery_days=recovery_days,
        per_year=per_year,
    )


def get_technicals(ticker_symbol: str) -> Optional[Technicals]:
    """
    Computes technical indicators using 5 years of OHLCV data.
    Uses FRED risk-free rate instead of hardcoded value.
    Returns rolling Sharpe distribution and detailed drawdown.
    """
    # Pull 5 years of data (1260 trading days)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")

    hist = vendor.get_ohlcv(ticker_symbol, start=start_date, end=end_date)

    if hist is None or hist.empty:
        logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=technicals | reason=no_ohlcv_data")
        return None

    try:
        close = hist['Close']
        returns = close.pct_change().dropna()

        if len(returns) < 10:
            logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=technicals | reason=insufficient_data | days={len(returns)}")
            return None

        rsi = compute_rsi(close)
        macd_signal = compute_macd(close)

        # Annualized volatility
        volatility = float(returns.std() * np.sqrt(252))

        # Fetch real risk-free rate from FRED
        rf_annual = _fetch_risk_free_rate()
        rf_daily = rf_annual / 252

        # Rolling Sharpe (252-day windows over the full history)
        rolling_sharpe = compute_rolling_sharpe(returns, rf_daily, window=252)

        # Legacy single-point Sharpe for backward compatibility (last 60 days)
        recent_returns = returns.tail(60)
        recent_excess = recent_returns - rf_daily
        sharpe_60d = float(np.sqrt(252) * recent_excess.mean() / recent_returns.std()) if recent_returns.std() != 0 else None

        # Detailed max drawdown
        max_dd = compute_max_drawdown(returns)

        # Legacy single-point drawdown (last 60 days)
        recent_cum = (1 + recent_returns).cumprod()
        recent_peak = recent_cum.expanding(min_periods=1).max()
        recent_dd = (recent_cum - recent_peak) / recent_peak
        max_drawdown_60d = float(recent_dd.min()) if not recent_dd.empty else None

        return Technicals(
            rsi_14=rsi,
            macd_signal=macd_signal,
            volatility_annualized=volatility,
            sharpe_rolling=rolling_sharpe,
            sharpe_60d=sharpe_60d,
            max_drawdown=max_dd,
            max_drawdown_60d=max_drawdown_60d,
            risk_free_rate=rf_annual,
            data_days=len(returns),
        )
    except Exception as e:
        logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker_symbol} | field=technicals | reason=computation_error | detail={e}")
        return None
