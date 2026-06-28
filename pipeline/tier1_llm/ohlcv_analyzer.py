"""
Tier 1C - raw OHLCV analyzer.

This module interprets raw yfinance OHLCV frames without calling an LLM. It is
designed to sit beside Tier 1A/1B as a market-structure read that Tier 2 can use
for tactical context.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd

from pipeline.infra.data_vendor import vendor
from pipeline.schemas.llm_schemas import RawOHLCVAnalysis

logger = logging.getLogger(__name__)

OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]


def _to_float(value: object) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _bounded(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(max(low, min(high, value)))


def preprocess_ohlcv(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert a raw yfinance frame into a clean business-day OHLCV frame.

    Handles yfinance MultiIndex columns and non-trading-day gaps. Prices are
    forward-filled across holiday gaps so rolling calculations operate on a
    regular business-day index.
    """
    if raw_df is None or raw_df.empty:
        raise ValueError("empty_ohlcv_frame")

    df = raw_df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        for level in range(df.columns.nlevels):
            values = set(str(v) for v in df.columns.get_level_values(level))
            if set(OHLCV_COLS).issubset(values):
                df.columns = df.columns.get_level_values(level)
                break
        else:
            df.columns = ["_".join(str(part) for part in col if part) for col in df.columns]

    missing = [col for col in OHLCV_COLS if col not in df.columns]
    if missing:
        raise ValueError(f"missing_ohlcv_columns:{','.join(missing)}")

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df = df[OHLCV_COLS].apply(pd.to_numeric, errors="coerce")
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=["Close"])

    if df.empty:
        raise ValueError("no_valid_close_prices")

    business_days = pd.bdate_range(start=df.index[0], end=df.index[-1])
    df = df.reindex(business_days).ffill().dropna(subset=["Close"])

    for col in ["Open", "High", "Low"]:
        df[col] = df[col].fillna(df["Close"])
    df["Volume"] = df["Volume"].fillna(0.0).clip(lower=0.0)

    if (df["Close"] <= 0).all():
        raise ValueError("non_positive_close_prices")

    return df


def _period_return(close: pd.Series, days: int) -> Optional[float]:
    if len(close) <= days:
        return None
    start = close.iloc[-days - 1]
    end = close.iloc[-1]
    if start <= 0 or pd.isna(start) or pd.isna(end):
        return None
    return float((end / start) - 1.0)


def _moving_average_alignment(close: pd.Series) -> tuple[str, Optional[float], Optional[float], Optional[float]]:
    ma_20 = _to_float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else None
    ma_50 = _to_float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    ma_200 = _to_float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    if ma_50 is None or ma_200 is None:
        return "unavailable", ma_20, ma_50, ma_200

    latest = float(close.iloc[-1])
    if latest > ma_50 > ma_200:
        return "bullish", ma_20, ma_50, ma_200
    if latest < ma_50 < ma_200:
        return "bearish", ma_20, ma_50, ma_200
    return "mixed", ma_20, ma_50, ma_200


def _annualized_log_slope(close: pd.Series, window: int = 63) -> Optional[float]:
    if len(close) < max(10, window):
        return None
    sample = close.tail(window)
    if (sample <= 0).any():
        return None
    x = np.arange(len(sample), dtype=float)
    slope = np.polyfit(x, np.log(sample.astype(float)), 1)[0]
    return float(np.exp(slope * 252) - 1.0)


def _volume_trend(close: pd.Series, volume: pd.Series) -> tuple[str, Optional[float]]:
    if len(volume) < 63:
        return "unavailable", None

    log_volume = np.log1p(volume.tail(63))
    vol_std = log_volume.std()
    zscore = None if vol_std == 0 or pd.isna(vol_std) else float((log_volume.iloc[-1] - log_volume.mean()) / vol_std)

    returns = close.diff().fillna(0.0)
    obv_direction = np.sign(returns)
    obv = (obv_direction * volume).cumsum()
    recent_obv = obv.tail(21)
    obv_slope = 0.0
    if len(recent_obv) >= 10 and recent_obv.std() != 0:
        obv_slope = float(np.polyfit(np.arange(len(recent_obv)), recent_obv, 1)[0])

    price_return_21d = _period_return(close, 21)
    high_volume = zscore is not None and zscore > 0.5

    if price_return_21d is not None and price_return_21d > 0 and (obv_slope > 0 or high_volume):
        return "accumulating", zscore
    if price_return_21d is not None and price_return_21d < 0 and (obv_slope < 0 or high_volume):
        return "distributing", zscore
    return "neutral", zscore


def _atr_pct_14d(df: pd.DataFrame) -> Optional[float]:
    if len(df) < 15:
        return None
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(14).mean().iloc[-1]
    latest = df["Close"].iloc[-1]
    if latest <= 0 or pd.isna(atr):
        return None
    return float(atr / latest)


def analyze_ohlcv_frame(ticker: str, raw_df: pd.DataFrame) -> RawOHLCVAnalysis:
    """Analyze one raw OHLCV frame and return a structured Tier 1C report."""
    warnings = []
    df = preprocess_ohlcv(raw_df)
    close = df["Close"]
    returns = close.pct_change().dropna()

    if len(close) < 63:
        warnings.append("less_than_63_business_days")
    if len(close) < 252:
        warnings.append("less_than_252_business_days")

    ret_5d = _period_return(close, 5)
    ret_21d = _period_return(close, 21)
    ret_63d = _period_return(close, 63)
    ret_126d = _period_return(close, 126)
    ret_252d = _period_return(close, 252)

    annualized_vol = _to_float(returns.std() * np.sqrt(252)) if not returns.empty else None
    downside = returns[returns < 0]
    downside_vol = _to_float(downside.std() * np.sqrt(252)) if len(downside) > 1 else None

    ma_alignment, ma_20, ma_50, ma_200 = _moving_average_alignment(close)
    slope = _annualized_log_slope(close)
    volume_signal, volume_zscore = _volume_trend(close, df["Volume"])

    score_parts = []
    if ret_21d is not None:
        score_parts.append(_bounded(ret_21d / 0.12, -1.0, 1.0))
    if ret_63d is not None:
        score_parts.append(_bounded(ret_63d / 0.25, -1.0, 1.0))
    if slope is not None:
        score_parts.append(_bounded(slope / 0.50, -1.0, 1.0))
    if ma_alignment == "bullish":
        score_parts.append(0.5)
    elif ma_alignment == "bearish":
        score_parts.append(-0.5)

    composite = float(np.mean(score_parts)) if score_parts else 0.0
    if composite >= 0.20:
        trend_direction = "bullish"
    elif composite <= -0.20:
        trend_direction = "bearish"
    else:
        trend_direction = "neutral"
    trend_strength = _bounded(abs(composite))

    trailing_252 = close.tail(252)
    high_52w = trailing_252.max()
    low_52w = trailing_252.min()
    latest_close = float(close.iloc[-1])
    drawdown = float((latest_close / high_52w) - 1.0) if high_52w > 0 else None
    if high_52w > low_52w:
        price_location = float((latest_close - low_52w) / (high_52w - low_52w))
        price_location = _bounded(price_location)
    else:
        price_location = None

    atr_pct = _atr_pct_14d(df)
    vol_bucket = "high_vol" if annualized_vol is not None and annualized_vol >= 0.35 else "low_vol"
    if trend_direction == "bullish":
        regime = f"trend_up_{vol_bucket}"
    elif trend_direction == "bearish":
        regime = f"trend_down_{vol_bucket}"
    else:
        regime = f"range_bound_{vol_bucket}"

    summary_signals = []
    if trend_direction != "neutral":
        summary_signals.append(f"{trend_direction}_price_trend")
    if ma_alignment in {"bullish", "bearish"}:
        summary_signals.append(f"{ma_alignment}_moving_average_stack")
    if volume_signal in {"accumulating", "distributing"}:
        summary_signals.append(f"volume_{volume_signal}")
    if drawdown is not None and drawdown <= -0.20:
        summary_signals.append("deep_drawdown_from_52w_high")
    if price_location is not None and price_location >= 0.80:
        summary_signals.append("near_52w_high")
    elif price_location is not None and price_location <= 0.20:
        summary_signals.append("near_52w_low")

    quality = 1.0
    if len(close) < 252:
        quality -= 0.20
    if len(close) < 63:
        quality -= 0.25
    if returns.empty:
        quality -= 0.30
    if df["Volume"].sum() <= 0:
        warnings.append("volume_unavailable_or_zero")
        quality -= 0.15

    return RawOHLCVAnalysis(
        ticker=ticker,
        as_of=str(date.today()),
        lookback_days=len(close),
        close=round(latest_close, 6),
        return_5d=ret_5d,
        return_21d=ret_21d,
        return_63d=ret_63d,
        return_126d=ret_126d,
        return_252d=ret_252d,
        annualized_volatility=annualized_vol,
        downside_volatility=downside_vol,
        trend_direction=trend_direction,
        trend_strength=round(trend_strength, 4),
        moving_average_alignment=ma_alignment,
        ma_20=ma_20,
        ma_50=ma_50,
        ma_200=ma_200,
        drawdown_from_52w_high=drawdown,
        price_location_52w=price_location,
        volume_zscore_63d=volume_zscore,
        volume_trend=volume_signal,
        atr_pct_14d=atr_pct,
        regime_label=regime,
        summary_signals=summary_signals,
        warnings=warnings,
        data_quality_score=round(_bounded(quality), 4),
    )


async def generate_ohlcv_analysis(
    raw_ohlcv_map: Dict[str, pd.DataFrame],
) -> Dict[str, RawOHLCVAnalysis]:
    """Async batch entry point for already-fetched raw yfinance OHLCV frames."""
    def _run_batch() -> Dict[str, RawOHLCVAnalysis]:
        results: Dict[str, RawOHLCVAnalysis] = {}
        for ticker, frame in raw_ohlcv_map.items():
            try:
                results[ticker] = analyze_ohlcv_frame(ticker, frame)
            except Exception as exc:
                logger.warning("Tier 1C OHLCV analysis failed for %s: %s", ticker, exc)
        return results

    return await asyncio.to_thread(_run_batch)


async def run_ohlcv_analyzer(
    tickers: Iterable[str],
    lookback_days: int = 730,
) -> Dict[str, RawOHLCVAnalysis]:
    """Fetch raw yfinance OHLCV through the vendor layer and run Tier 1C."""
    end = date.today() + timedelta(days=1)
    start = end - timedelta(days=lookback_days)

    async def _fetch_one(ticker: str) -> tuple[str, Optional[pd.DataFrame]]:
        frame = await asyncio.to_thread(
            vendor.get_ohlcv,
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
        )
        return ticker, frame

    pairs = await asyncio.gather(*(_fetch_one(ticker) for ticker in tickers))
    raw_map = {ticker: frame for ticker, frame in pairs if frame is not None and not frame.empty}
    return await generate_ohlcv_analysis(raw_map)
