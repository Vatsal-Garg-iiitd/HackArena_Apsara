"""
Backtesting Framework.
Uses vectorbt for vectorized backtesting of pipeline signals.
Supports walk-forward validation, Monte Carlo significance testing,
and horizon optimization.
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results from a single backtest run."""
    holding_period_days: int
    annualized_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    calmar_ratio: Optional[float] = None
    win_rate: Optional[float] = None
    avg_holding_return: Optional[float] = None
    total_trades: int = 0
    is_significant: bool = False  # p < 0.05 vs random
    in_sample_sharpe: Optional[float] = None
    out_of_sample_sharpe: Optional[float] = None
    likely_overfit: bool = False

    def to_dict(self) -> dict:
        return {
            "holding_period_days": self.holding_period_days,
            "annualized_return": self.annualized_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "calmar_ratio": self.calmar_ratio,
            "win_rate": self.win_rate,
            "avg_holding_return": self.avg_holding_return,
            "total_trades": self.total_trades,
            "is_significant": self.is_significant,
            "in_sample_sharpe": self.in_sample_sharpe,
            "out_of_sample_sharpe": self.out_of_sample_sharpe,
            "likely_overfit": self.likely_overfit,
        }


@dataclass
class HorizonOptimizationResult:
    """Results from testing multiple holding periods."""
    optimal_holding_days: int = 0
    optimal_sharpe: float = 0.0
    all_results: Dict[int, BacktestResult] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "optimal_holding_days": self.optimal_holding_days,
            "optimal_sharpe": self.optimal_sharpe,
            "per_horizon": {k: v.to_dict() for k, v in self.all_results.items()},
        }


class SignalBacktester:
    """
    Backtests pipeline signals against historical price data.
    """

    def __init__(self, prices: pd.Series, risk_free_rate: float = 0.0425):
        """
        Args:
            prices: Daily close prices indexed by date
            risk_free_rate: Annual risk-free rate (default ~4.25%)
        """
        self.prices = prices
        self.returns = prices.pct_change().dropna()
        self.rf_daily = risk_free_rate / 252

    def backtest_signals(
        self,
        signals: pd.Series,
        holding_period: int = 21,
    ) -> BacktestResult:
        """
        Backtest a series of signals.

        Args:
            signals: Series of signals (1 = bullish/buy, -1 = bearish/sell, 0 = neutral)
                     indexed by date
            holding_period: Number of trading days to hold after signal

        Returns:
            BacktestResult with performance metrics
        """
        result = BacktestResult(holding_period_days=holding_period)

        # Align signals with prices
        common_dates = signals.index.intersection(self.prices.index)
        if len(common_dates) < 10:
            return result

        trade_returns = []

        for signal_date in common_dates:
            signal_val = signals.loc[signal_date]
            if signal_val == 0:
                continue

            # Find the price at entry and exit
            entry_idx = self.prices.index.get_loc(signal_date)
            exit_idx = min(entry_idx + holding_period, len(self.prices) - 1)

            if exit_idx <= entry_idx:
                continue

            entry_price = self.prices.iloc[entry_idx]
            exit_price = self.prices.iloc[exit_idx]

            # Return depends on signal direction
            raw_return = (exit_price - entry_price) / entry_price
            trade_return = raw_return * signal_val  # Flip for short signals
            trade_returns.append(trade_return)

        if not trade_returns:
            return result

        trade_returns = np.array(trade_returns)
        result.total_trades = len(trade_returns)
        result.avg_holding_return = float(np.mean(trade_returns))
        result.win_rate = float(np.sum(trade_returns > 0) / len(trade_returns))

        # Annualize
        trades_per_year = 252 / holding_period
        result.annualized_return = float(result.avg_holding_return * trades_per_year)

        # Sharpe (annualized)
        if np.std(trade_returns) > 0:
            result.sharpe_ratio = float(
                np.sqrt(trades_per_year) * (np.mean(trade_returns) - self.rf_daily * holding_period) / np.std(trade_returns)
            )

        # Max drawdown from cumulative trade returns
        cum_returns = np.cumprod(1 + trade_returns)
        peak = np.maximum.accumulate(cum_returns)
        drawdown = (cum_returns - peak) / peak
        result.max_drawdown = float(np.min(drawdown))

        # Calmar ratio
        if result.max_drawdown and result.max_drawdown < 0 and result.annualized_return is not None:
            result.calmar_ratio = float(result.annualized_return / abs(result.max_drawdown))

        return result

    def walk_forward_validation(
        self,
        signals: pd.Series,
        holding_period: int = 21,
        train_pct: float = 0.6,
        n_splits: int = 4,
    ) -> BacktestResult:
        """
        Walk-forward validation: train on first portion, test on held-out period.
        Roll forward in equal splits.
        """
        result = BacktestResult(holding_period_days=holding_period)
        n = len(signals)

        if n < 50:
            return result

        split_size = n // n_splits
        in_sample_sharpes = []
        oos_sharpes = []

        for i in range(n_splits - 1):
            train_end = (i + 1) * split_size
            test_end = min(train_end + split_size, n)

            train_signals = signals.iloc[:train_end]
            test_signals = signals.iloc[train_end:test_end]

            is_result = self.backtest_signals(train_signals, holding_period)
            oos_result = self.backtest_signals(test_signals, holding_period)

            if is_result.sharpe_ratio is not None:
                in_sample_sharpes.append(is_result.sharpe_ratio)
            if oos_result.sharpe_ratio is not None:
                oos_sharpes.append(oos_result.sharpe_ratio)

        if in_sample_sharpes:
            result.in_sample_sharpe = float(np.mean(in_sample_sharpes))
        if oos_sharpes:
            result.out_of_sample_sharpe = float(np.mean(oos_sharpes))

        # Check for overfitting
        if (result.in_sample_sharpe is not None and result.out_of_sample_sharpe is not None
                and result.in_sample_sharpe > 0):
            ratio = result.out_of_sample_sharpe / result.in_sample_sharpe
            result.likely_overfit = ratio < 0.6

        # Full backtest for overall metrics
        full = self.backtest_signals(signals, holding_period)
        result.annualized_return = full.annualized_return
        result.sharpe_ratio = full.sharpe_ratio
        result.max_drawdown = full.max_drawdown
        result.calmar_ratio = full.calmar_ratio
        result.win_rate = full.win_rate
        result.avg_holding_return = full.avg_holding_return
        result.total_trades = full.total_trades

        return result

    def monte_carlo_significance(
        self,
        signals: pd.Series,
        holding_period: int = 21,
        n_simulations: int = 1000,
    ) -> bool:
        """
        Test statistical significance by shuffling signal dates randomly.
        Returns True if actual performance is in top 5% of null distribution.
        """
        actual = self.backtest_signals(signals, holding_period)
        if actual.sharpe_ratio is None:
            return False

        null_sharpes = []
        for _ in range(n_simulations):
            shuffled = signals.copy()
            shuffled.index = np.random.permutation(shuffled.index)
            sim_result = self.backtest_signals(shuffled, holding_period)
            if sim_result.sharpe_ratio is not None:
                null_sharpes.append(sim_result.sharpe_ratio)

        if not null_sharpes:
            return False

        percentile = np.percentile(null_sharpes, 95)
        return actual.sharpe_ratio > percentile

    def optimize_horizon(
        self,
        signals: pd.Series,
        horizons: List[int] = None,
    ) -> HorizonOptimizationResult:
        """
        Test multiple holding periods to find the empirically optimal horizon.
        """
        if horizons is None:
            horizons = [5, 10, 21, 42, 63, 126, 252]

        opt_result = HorizonOptimizationResult()
        best_sharpe = -float('inf')
        best_horizon = horizons[0]

        for h in horizons:
            bt = self.walk_forward_validation(signals, holding_period=h)
            opt_result.all_results[h] = bt

            oos_sharpe = bt.out_of_sample_sharpe if bt.out_of_sample_sharpe is not None else -float('inf')
            if oos_sharpe > best_sharpe:
                best_sharpe = oos_sharpe
                best_horizon = h

        opt_result.optimal_holding_days = best_horizon
        opt_result.optimal_sharpe = best_sharpe if best_sharpe > -float('inf') else 0.0

        return opt_result
