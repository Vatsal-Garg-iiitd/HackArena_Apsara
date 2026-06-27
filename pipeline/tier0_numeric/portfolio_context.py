"""
Portfolio Correlation & Concentration Analysis.
Computes pairwise correlation with existing holdings, factor exposure impact,
and variance contribution to guide position sizing.
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pipeline.infra.data_vendor import vendor

logger = logging.getLogger(__name__)


class PortfolioContextReport:
    """Results of portfolio impact analysis."""
    def __init__(self):
        self.correlations: Dict[str, float] = {}  # holding_ticker -> correlation
        self.max_correlation: Optional[float] = None
        self.max_correlation_ticker: Optional[str] = None
        self.concentration_warnings: List[str] = []
        self.variance_contribution_2pct: Optional[float] = None  # % of portfolio variance at 2% sizing
        self.recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "correlations": self.correlations,
            "max_correlation": self.max_correlation,
            "max_correlation_ticker": self.max_correlation_ticker,
            "concentration_warnings": self.concentration_warnings,
            "variance_contribution_2pct": self.variance_contribution_2pct,
            "recommendation": self.recommendation,
        }


def analyze_portfolio_context(
    candidate_ticker: str,
    existing_holdings: List[str],
    holding_weights: Optional[Dict[str, float]] = None,
) -> Optional[PortfolioContextReport]:
    """
    Analyze how adding a candidate stock affects portfolio diversification.

    Args:
        candidate_ticker: The stock being considered
        existing_holdings: List of tickers currently held
        holding_weights: Optional dict of ticker -> portfolio weight (0-1).
                        If None, assumes equal weight.
    """
    if not existing_holdings:
        report = PortfolioContextReport()
        report.recommendation = "No existing holdings to analyze correlation against."
        return report

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    # Fetch candidate returns
    candidate_hist = vendor.get_ohlcv(candidate_ticker, start=start_date, end=end_date)
    if candidate_hist is None or len(candidate_hist) < 20:
        return None

    candidate_returns = candidate_hist["Close"].pct_change().dropna()

    report = PortfolioContextReport()

    # Compute pairwise correlations
    max_corr = -1.0
    max_corr_ticker = ""

    for holding in existing_holdings:
        holding_hist = vendor.get_ohlcv(holding, start=start_date, end=end_date)
        if holding_hist is None or len(holding_hist) < 20:
            continue

        holding_returns = holding_hist["Close"].pct_change().dropna()

        # Align dates
        combined = pd.DataFrame({
            "candidate": candidate_returns,
            "holding": holding_returns,
        }).dropna()

        if len(combined) < 20:
            continue

        correlation = float(combined["candidate"].corr(combined["holding"]))
        report.correlations[holding] = round(correlation, 4)

        if abs(correlation) > abs(max_corr):
            max_corr = correlation
            max_corr_ticker = holding

    report.max_correlation = round(max_corr, 4) if max_corr > -1.0 else None
    report.max_correlation_ticker = max_corr_ticker if max_corr_ticker else None

    # Concentration warnings
    HIGH_CORR_THRESHOLD = 0.7
    for ticker, corr in report.correlations.items():
        if corr > HIGH_CORR_THRESHOLD:
            report.concentration_warnings.append(
                f"High correlation ({corr:.2f}) with existing holding {ticker}. "
                f"Adding this position increases concentration risk rather than diversification."
            )

    # Simple variance contribution estimate at 2% sizing
    if holding_weights and candidate_returns is not None:
        candidate_var = float(candidate_returns.var() * 252)
        weight = 0.02  # 2% of portfolio
        # Marginal variance contribution (simplified)
        report.variance_contribution_2pct = round(weight ** 2 * candidate_var * 10000, 4)

    # Build recommendation
    if report.concentration_warnings:
        report.recommendation = (
            f"CAUTION: {candidate_ticker} has high correlation with existing holdings. "
            f"Consider smaller position sizing to manage concentration risk."
        )
    elif report.max_correlation is not None and report.max_correlation < 0.3:
        report.recommendation = (
            f"{candidate_ticker} provides good diversification benefit "
            f"(max correlation {report.max_correlation:.2f} with {report.max_correlation_ticker})."
        )
    else:
        report.recommendation = (
            f"{candidate_ticker} has moderate correlation with portfolio. "
            f"Standard position sizing appropriate."
        )

    return report
