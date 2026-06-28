"""
Tier 1C - raw OHLCV analyzer with optional Moirai 1.1-R forecasting.

This module interprets raw yfinance OHLCV frames and, when the optional Moirai
dependencies are installed, runs Salesforce Moirai 1.1-R as the multivariate
OHLCV forecasting layer. Moirai 1.1 is used intentionally because Moirai 2.0
removed multivariate support.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from functools import lru_cache
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd

from pipeline.infra.data_vendor import vendor
from pipeline.schemas.llm_schemas import RawOHLCVAnalysis

logger = logging.getLogger(__name__)

OHLCV_COLS = ["Open", "High", "Low", "Close", "Volume"]
CLOSE_IDX = 3


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


@lru_cache(maxsize=3)
def _get_moirai_model(size: str, context_length: int, prediction_length: int):
    """
    Load and cache Moirai 1.1-R.

    The import happens lazily so local tests and API routes still work when the
    heavyweight optional forecasting dependencies are not installed.
    """
    from uni2ts.model.moirai import MoiraiForecast, MoiraiModule

    model_name = f"Salesforce/moirai-1.1-R-{size}"
    logger.info("Loading %s for Tier 1C OHLCV forecasting", model_name)
    return MoiraiForecast(
        module=MoiraiModule.from_pretrained(model_name),
        prediction_length=prediction_length,
        context_length=context_length,
        patch_size="auto",
        num_samples=100,
        target_dim=5,
        feat_dynamic_real_dim=0,
        past_feat_dynamic_real_dim=0,
    )


def _prepare_moirai_frame(df: pd.DataFrame) -> pd.DataFrame:
    model_df = df[OHLCV_COLS].copy()
    model_df["Volume"] = np.log1p(model_df["Volume"].clip(lower=0.0))
    return model_df


def _infer_moirai_batch(
    frames: Dict[str, pd.DataFrame],
    model_size: str,
    context_length: int,
    prediction_length: int,
) -> Dict[str, Dict[str, float]]:
    from gluonts.dataset.pandas import PandasDataset
    from gluonts.dataset.split import split

    eligible = {
        ticker: _prepare_moirai_frame(frame)
        for ticker, frame in frames.items()
        if len(frame) >= context_length + prediction_length
    }
    if not eligible:
        return {}

    model = _get_moirai_model(model_size, context_length, prediction_length)
    ds = PandasDataset(eligible, target=OHLCV_COLS, freq="B")
    _, test_template = split(ds, offset=-prediction_length)
    test_data = test_template.generate_instances(
        prediction_length=prediction_length,
        windows=1,
    )

    predictor = model.create_predictor(batch_size=max(1, len(eligible)))
    forecasts = list(predictor.predict(test_data.input))

    results: Dict[str, Dict[str, float]] = {}
    for ticker, forecast in zip(eligible.keys(), forecasts):
        samples = forecast.samples
        if samples.ndim == 3:
            close_samples = samples[:, :, CLOSE_IDX]
        elif samples.ndim == 2:
            close_samples = samples
        else:
            raise ValueError(f"unexpected_moirai_samples_shape:{samples.shape}")

        close_dist_5d = close_samples[:, -1]
        current_close = float(frames[ticker]["Close"].iloc[-1])
        if current_close <= 0:
            continue

        results[ticker] = {
            "moirai_implied_return_5d": float((np.median(close_dist_5d) - current_close) / current_close),
            "moirai_implied_volatility": float(np.std(close_dist_5d) / current_close),
            "moirai_directional_confidence": float(np.mean(close_dist_5d > current_close)),
            "moirai_regime_uncertainty": float(
                (np.percentile(close_dist_5d, 75) - np.percentile(close_dist_5d, 25)) / current_close
            ),
        }

    return results


async def _generate_moirai_forecasts(
    processed_frames: Dict[str, pd.DataFrame],
    model_size: str,
    context_length: int,
    prediction_length: int,
) -> tuple[Dict[str, Dict[str, float]], Optional[str]]:
    try:
        return await asyncio.to_thread(
            _infer_moirai_batch,
            processed_frames,
            model_size,
            context_length,
            prediction_length,
        ), None
    except ImportError as exc:
        return {}, f"moirai_unavailable:{exc.__class__.__name__}:{exc}"
    except Exception as exc:
        logger.warning("Moirai Tier 1C forecast failed: %s", exc)
        return {}, f"moirai_failed:{exc.__class__.__name__}:{exc}"


def analyze_processed_ohlcv_frame(ticker: str, df: pd.DataFrame) -> RawOHLCVAnalysis:
    """Analyze a cleaned OHLCV frame and return a structured Tier 1C report."""
    warnings = []
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


def analyze_ohlcv_frame(ticker: str, raw_df: pd.DataFrame) -> RawOHLCVAnalysis:
    """Analyze one raw OHLCV frame without running Moirai batch inference."""
    return analyze_processed_ohlcv_frame(ticker, preprocess_ohlcv(raw_df))


async def generate_ohlcv_analysis(
    raw_ohlcv_map: Dict[str, pd.DataFrame],
    use_moirai: bool = True,
    moirai_model_size: str = "small",
    context_length: int = 252,
    prediction_length: int = 5,
) -> Dict[str, RawOHLCVAnalysis]:
    """Async batch entry point for raw yfinance OHLCV frames."""
    def _run_batch() -> Dict[str, RawOHLCVAnalysis]:
        results: Dict[str, RawOHLCVAnalysis] = {}
        processed: Dict[str, pd.DataFrame] = {}
        for ticker, frame in raw_ohlcv_map.items():
            try:
                processed[ticker] = preprocess_ohlcv(frame)
                results[ticker] = analyze_processed_ohlcv_frame(ticker, processed[ticker])
            except Exception as exc:
                logger.warning("Tier 1C OHLCV analysis failed for %s: %s", ticker, exc)
        return results, processed

    results, processed = await asyncio.to_thread(_run_batch)

    if not use_moirai or not processed:
        if not use_moirai:
            results = {
                ticker: report.model_copy(update={"moirai_status": "not_run"})
                for ticker, report in results.items()
            }
        return results

    model_name = f"Salesforce/moirai-1.1-R-{moirai_model_size}"
    forecasts, error = await _generate_moirai_forecasts(
        processed,
        moirai_model_size,
        context_length,
        prediction_length,
    )

    updated: Dict[str, RawOHLCVAnalysis] = {}
    for ticker, report in results.items():
        warnings = list(report.warnings)
        if ticker in forecasts:
            updated[ticker] = report.model_copy(
                update={
                    **forecasts[ticker],
                    "moirai_status": "ok",
                    "moirai_model": model_name,
                    "summary_signals": report.summary_signals + ["moirai_forecast_available"],
                }
            )
        else:
            if error:
                status = "unavailable" if error.startswith("moirai_unavailable") else "failed"
                warnings.append(error)
            else:
                status = "failed"
                warnings.append("moirai_failed:insufficient_context_or_no_forecast")
            updated[ticker] = report.model_copy(
                update={
                    "moirai_status": status,
                    "moirai_model": model_name,
                    "warnings": warnings,
                }
            )

    return updated


async def generate_moirai_signals(
    raw_ohlcv_map: Dict[str, pd.DataFrame],
    model_size: str = "small",
    context_length: int = 252,
    prediction_length: int = 5,
) -> Dict[str, RawOHLCVAnalysis]:
    """Compatibility entry point for explicitly Moirai-backed Tier 1C runs."""
    return await generate_ohlcv_analysis(
        raw_ohlcv_map,
        use_moirai=True,
        moirai_model_size=model_size,
        context_length=context_length,
        prediction_length=prediction_length,
    )


async def run_ohlcv_analyzer(
    tickers: Iterable[str],
    lookback_days: int = 730,
    use_moirai: bool = True,
    moirai_model_size: str = "small",
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
    return await generate_ohlcv_analysis(
        raw_map,
        use_moirai=use_moirai,
        moirai_model_size=moirai_model_size,
    )
