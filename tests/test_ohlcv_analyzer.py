import asyncio
import unittest

import numpy as np
import pandas as pd

from pipeline.tier1_llm.ohlcv_analyzer import (
    analyze_ohlcv_frame,
    generate_ohlcv_analysis,
    generate_moirai_signals,
    preprocess_ohlcv,
)


def _sample_ohlcv(rows: int = 300, direction: float = 1.0) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-01", periods=rows)
    base = np.linspace(100.0, 145.0 if direction > 0 else 75.0, rows)
    wave = np.sin(np.arange(rows) / 9.0) * 1.5
    close = base + wave
    open_ = close * 0.995
    high = close * 1.015
    low = close * 0.985
    volume = np.linspace(1_000_000, 2_000_000 if direction > 0 else 800_000, rows)
    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=index,
    )


class RawOHLCVAnalyzerTests(unittest.TestCase):
    def test_preprocess_handles_yfinance_multiindex_columns(self):
        frame = _sample_ohlcv(80)
        frame = frame.drop(frame.index[10])
        frame.columns = pd.MultiIndex.from_product([frame.columns, ["AAPL"]])

        clean = preprocess_ohlcv(frame)

        self.assertEqual(list(clean.columns), ["Open", "High", "Low", "Close", "Volume"])
        self.assertGreater(len(clean), len(frame))
        self.assertFalse(clean["Close"].isna().any())

    def test_analyze_detects_bullish_ohlcv_structure(self):
        report = analyze_ohlcv_frame("AAPL", _sample_ohlcv())

        self.assertEqual(report.ticker, "AAPL")
        self.assertEqual(report.trend_direction, "bullish")
        self.assertGreater(report.trend_strength, 0.2)
        self.assertGreater(report.return_21d, 0)
        self.assertIn(report.moving_average_alignment, {"bullish", "mixed"})
        self.assertGreaterEqual(report.data_quality_score, 0.8)

    def test_async_batch_skips_invalid_frames(self):
        with self.assertLogs("pipeline.tier1_llm.ohlcv_analyzer", level="WARNING"):
            result = asyncio.run(
                generate_ohlcv_analysis(
                    {
                        "UP": _sample_ohlcv(),
                        "EMPTY": pd.DataFrame(),
                    },
                    use_moirai=False,
                )
            )

        self.assertIn("UP", result)
        self.assertNotIn("EMPTY", result)

    def test_moirai_path_marks_unavailable_when_dependencies_missing(self):
        result = asyncio.run(generate_moirai_signals({"UP": _sample_ohlcv()}))

        self.assertIn("UP", result)
        self.assertIn(result["UP"].moirai_status, {"ok", "unavailable", "failed"})
        if result["UP"].moirai_status != "ok":
            self.assertTrue(any("moirai_" in warning for warning in result["UP"].warnings))


if __name__ == "__main__":
    unittest.main()
