"""
Data Vendor Abstraction Layer.

Uses yfinance as the sole data source for Indian and global equities.
All methods return None on failure instead of 0.0 to prevent silent data corruption.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

import pandas as pd

logger = logging.getLogger(__name__)


class DataVendorClient(ABC):
    """Abstract base class for all data vendors."""

    @abstractmethod
    def get_financials(self, ticker: str, period: str = "quarterly") -> Optional[Dict[str, pd.DataFrame]]:
        """
        Returns a dict with keys: 'balance_sheet', 'financials', 'cash_flow'.
        Each value is a pandas DataFrame. Returns None on failure.
        """
        pass

    @abstractmethod
    def get_ohlcv(self, ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """
        Returns OHLCV DataFrame with columns: Open, High, Low, Close, Volume.
        Index is DatetimeIndex. Returns None on failure.
        """
        pass

    @abstractmethod
    def get_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Returns ticker info dict (sector, industry, market cap, short interest, etc.).
        Returns None on failure.
        """
        pass

    @abstractmethod
    def get_insider_transactions(self, ticker: str) -> Optional[pd.DataFrame]:
        """
        Returns insider transactions DataFrame. Returns None on failure.
        """
        pass

    @abstractmethod
    def get_options_chain(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Returns options chain data. Returns None on failure.
        """
        pass


class YFinanceVendor(DataVendorClient):
    """
    YFinance-based data vendor for NSE/BSE (.NS/.BO) and other markets.
    Wraps yfinance with proper None-propagation instead of 0.0 fallbacks.
    """

    def get_financials(self, ticker: str, period: str = "quarterly") -> Optional[Dict[str, pd.DataFrame]]:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)

            if period == "quarterly":
                balance_sheet = t.quarterly_balance_sheet
                financials = t.quarterly_financials
                cash_flow = t.quarterly_cash_flow
            else:
                balance_sheet = t.balance_sheet
                financials = t.financials
                cash_flow = t.cashflow

            if balance_sheet is None or balance_sheet.empty:
                logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=balance_sheet | reason=yfinance_empty")
                return None

            return {
                "balance_sheet": balance_sheet,
                "financials": financials if financials is not None else pd.DataFrame(),
                "cash_flow": cash_flow if cash_flow is not None else pd.DataFrame(),
            }
        except Exception as e:
            logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=financials | reason=yfinance_error | detail={e}")
            return None

    def get_ohlcv(self, ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            hist = t.history(start=start, end=end)
            if hist is None or hist.empty:
                logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=ohlcv | reason=yfinance_empty")
                return None
            return hist
        except Exception as e:
            logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=ohlcv | reason=yfinance_error | detail={e}")
            return None

    def get_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info
            if not info or info.get("regularMarketPrice") is None:
                logger.warning(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=info | reason=yfinance_empty")
                return None
            return info
        except Exception as e:
            logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=info | reason=yfinance_error | detail={e}")
            return None

    def get_insider_transactions(self, ticker: str) -> Optional[pd.DataFrame]:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            txns = t.insider_transactions
            if txns is None or txns.empty:
                return None
            return txns
        except Exception as e:
            logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=insider_transactions | reason=yfinance_error | detail={e}")
            return None

    def get_options_chain(self, ticker: str) -> Optional[Dict[str, Any]]:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            expirations = t.options
            if not expirations:
                return None
            chains = {}
            for exp in expirations[:3]:
                chain = t.option_chain(exp)
                chains[exp] = {
                    "calls": chain.calls,
                    "puts": chain.puts,
                }
            return {"expirations": list(expirations[:3]), "chains": chains}
        except Exception as e:
            logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=options | reason=yfinance_error | detail={e}")
            return None


class CachedDataVendor(DataVendorClient):
    """
    Data Vendor wrapper that intercepts get_ohlcv requests, checks cache,
    and only fetches the delta from the last cached date forward.
    """

    def __init__(self, inner_vendor: DataVendorClient):
        self.inner = inner_vendor

    def get_financials(self, ticker: str, period: str = "quarterly") -> Optional[Dict[str, pd.DataFrame]]:
        return self.inner.get_financials(ticker, period)

    def get_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self.inner.get_info(ticker)

    def get_insider_transactions(self, ticker: str) -> Optional[pd.DataFrame]:
        return self.inner.get_insider_transactions(ticker)

    def get_options_chain(self, ticker: str) -> Optional[Dict[str, Any]]:
        return self.inner.get_options_chain(ticker)

    def get_ohlcv(self, ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
        from pipeline.infra.cache import cache
        import datetime

        try:
            start_date = datetime.datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end, "%Y-%m-%d").date()
        except Exception:
            return self.inner.get_ohlcv(ticker, start, end)

        cached_df = cache.get_cached_ohlcv(ticker, start, end)
        latest_cached = cache.get_latest_ohlcv_date(ticker)
        today = datetime.date.today()

        needs_delta = False
        delta_start = start

        if latest_cached is None:
            needs_delta = True
            delta_start = start
        elif latest_cached < end_date and latest_cached < today:
            needs_delta = True
            delta_start_date = latest_cached + datetime.timedelta(days=1)
            delta_start = delta_start_date.strftime("%Y-%m-%d")

        if needs_delta:
            logger.info(f"OHLCV_CACHE_MISS | ticker={ticker} | fetching_delta_from={delta_start}_to={end}")
            delta_df = self.inner.get_ohlcv(ticker, delta_start, end)

            if delta_df is not None and not delta_df.empty:
                cache.save_ohlcv(ticker, delta_df)
                cached_df = cache.get_cached_ohlcv(ticker, start, end)
        else:
            logger.info(f"OHLCV_CACHE_HIT | ticker={ticker} | range={start}_to={end}")

        return cached_df


def get_data_vendor() -> DataVendorClient:
    """Factory function. Returns yfinance wrapped in CachedDataVendor."""
    return CachedDataVendor(YFinanceVendor())


# Global vendor instance
vendor = get_data_vendor()
