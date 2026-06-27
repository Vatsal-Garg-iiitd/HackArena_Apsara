"""
Data Vendor Abstraction Layer.

Replaces direct yfinance coupling with an abstract interface.
Concrete implementations: YFinanceVendor (fallback), PolygonVendor (primary).
All methods return None on failure instead of 0.0 to prevent silent data corruption.
"""

import os
import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class DataRetrievalError(Exception):
    """Raised when a data fetch fails in a way that should not be silently ignored."""
    pass


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
    YFinance-based data vendor. Used as fallback when Polygon is unavailable.
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
            # Get up to 3 nearest expirations
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


class PolygonVendor(DataVendorClient):
    """
    Polygon.io data vendor. Primary production data source.
    Uses structured GAAP financial data from SEC XBRL filings and
    clean OHLCV data with proper corporate action adjustments.
    """

    BASE_URL = "https://api.polygon.io"

    def __init__(self):
        self.api_key = os.getenv("POLYGON_API_KEY", "")
        if not self.api_key:
            raise DataRetrievalError("POLYGON_API_KEY not found in environment")

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated request to Polygon API."""
        if params is None:
            params = {}
        params["apiKey"] = self.api_key

        try:
            url = f"{self.BASE_URL}{endpoint}"
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning(f"Polygon rate limited on {endpoint}")
                return None
            else:
                logger.error(f"Polygon API error {response.status_code} on {endpoint}: {response.text[:200]}")
                return None
        except requests.exceptions.Timeout:
            logger.error(f"Polygon timeout on {endpoint}")
            return None
        except Exception as e:
            logger.error(f"Polygon request error on {endpoint}: {e}")
            return None

    def get_financials(self, ticker: str, period: str = "quarterly") -> Optional[Dict[str, pd.DataFrame]]:
        """
        Fetch structured GAAP financials from Polygon's /vX/reference/financials endpoint.
        Returns data structured to match yfinance format for compatibility.
        Falls back to YFinanceVendor on rate limits or failures.
        """
        timeframe = "quarterly" if period == "quarterly" else "annual"
        data = self._request(f"/vX/reference/financials", {
            "ticker": ticker,
            "timeframe": timeframe,
            "limit": 8,
            "order": "desc",
            "sort": "period_of_report_date",
        })

        if not data or "results" not in data or not data["results"]:
            logger.warning(f"Polygon financials failed or rate limited for {ticker}. Falling back to YFinance.")
            try:
                yf_vendor = YFinanceVendor()
                return yf_vendor.get_financials(ticker, period)
            except Exception as e:
                logger.error(f"Fallback to YFinance financials failed for {ticker}: {e}")
                return None

        try:
            # Parse Polygon's nested financial structure into DataFrames
            balance_rows = {}
            income_rows = {}
            cashflow_rows = {}

            for filing in data["results"]:
                period_date = pd.Timestamp(filing.get("end_date", filing.get("period_of_report_date", "")))
                fin = filing.get("financials", {})

                # Balance sheet
                bs = fin.get("balance_sheet", {})
                for key, val_obj in bs.items():
                    label = val_obj.get("label", key)
                    value = val_obj.get("value")
                    if label not in balance_rows:
                        balance_rows[label] = {}
                    balance_rows[label][period_date] = value

                # Income statement
                inc = fin.get("income_statement", {})
                for key, val_obj in inc.items():
                    label = val_obj.get("label", key)
                    value = val_obj.get("value")
                    if label not in income_rows:
                        income_rows[label] = {}
                    income_rows[label][period_date] = value

                # Cash flow
                cf = fin.get("cash_flow_statement", {})
                for key, val_obj in cf.items():
                    label = val_obj.get("label", key)
                    value = val_obj.get("value")
                    if label not in cashflow_rows:
                        cashflow_rows[label] = {}
                    cashflow_rows[label][period_date] = value

            balance_sheet = pd.DataFrame(balance_rows).T if balance_rows else pd.DataFrame()
            financials = pd.DataFrame(income_rows).T if income_rows else pd.DataFrame()
            cash_flow = pd.DataFrame(cashflow_rows).T if cashflow_rows else pd.DataFrame()

            # Sort columns (dates) descending to match yfinance convention
            for df in [balance_sheet, financials, cash_flow]:
                if not df.empty:
                    df.sort_index(axis=1, ascending=False, inplace=True)

            return {
                "balance_sheet": balance_sheet,
                "financials": financials,
                "cash_flow": cash_flow,
            }
        except Exception as e:
            logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=financials | reason=polygon_parse_error | detail={e}")
            # Try to fall back even on parse errors
            try:
                yf_vendor = YFinanceVendor()
                return yf_vendor.get_financials(ticker, period)
            except Exception:
                return None

    def get_ohlcv(self, ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data from Polygon's /v2/aggs endpoint.
        Returns properly adjusted data with corporate action adjustments.
        Falls back to YFinanceVendor on rate limits or failures.
        """
        data = self._request(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
            {"adjusted": "true", "sort": "asc", "limit": 5000}
        )

        if not data or "results" not in data or not data["results"]:
            logger.warning(f"Polygon OHLCV failed or rate limited for {ticker}. Falling back to YFinance.")
            try:
                yf_vendor = YFinanceVendor()
                return yf_vendor.get_ohlcv(ticker, start, end)
            except Exception as e:
                logger.error(f"Fallback to YFinance OHLCV failed for {ticker}: {e}")
                return None

        try:
            results = data["results"]
            df = pd.DataFrame(results)
            df["Date"] = pd.to_datetime(df["t"], unit="ms")
            df.set_index("Date", inplace=True)
            df.rename(columns={
                "o": "Open",
                "h": "High",
                "l": "Low",
                "c": "Close",
                "v": "Volume",
            }, inplace=True)
            return df[["Open", "High", "Low", "Close", "Volume"]]
        except Exception as e:
            logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=ohlcv | reason=polygon_parse_error | detail={e}")
            try:
                yf_vendor = YFinanceVendor()
                return yf_vendor.get_ohlcv(ticker, start, end)
            except Exception:
                return None

    def get_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetch ticker details from Polygon's reference endpoint.
        Falls back to YFinanceVendor on rate limits or failures.
        """
        data = self._request(f"/v3/reference/tickers/{ticker}")

        if not data or "results" not in data:
            logger.warning(f"Polygon info failed or rate limited for {ticker}. Falling back to YFinance.")
            try:
                yf_vendor = YFinanceVendor()
                return yf_vendor.get_info(ticker)
            except Exception as e:
                logger.error(f"Fallback to YFinance info failed for {ticker}: {e}")
                return None

        results = data["results"]
        return {
            "shortName": results.get("name"),
            "sector": results.get("sic_description"),
            "industry": results.get("sic_description"),
            "marketCap": results.get("market_cap"),
            "sicCode": results.get("sic_code"),
            "primaryExchange": results.get("primary_exchange"),
            "type": results.get("type"),
            "cik": results.get("cik"),
            "locale": results.get("locale"),
        }

    def get_insider_transactions(self, ticker: str) -> Optional[pd.DataFrame]:
        """Polygon doesn't have a direct insider transactions endpoint on starter tier."""
        # Fall back to yfinance for this specific data point
        yf_vendor = YFinanceVendor()
        return yf_vendor.get_insider_transactions(ticker)

    def get_options_chain(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetch options contracts from Polygon.
        Falls back to YFinanceVendor on rate limits or failures.
        """
        data = self._request(f"/v3/reference/options/contracts", {
            "underlying_ticker": ticker,
            "expired": "false",
            "limit": 250,
            "order": "asc",
            "sort": "expiration_date",
        })

        if not data or "results" not in data or not data["results"]:
            logger.warning(f"Polygon options failed or rate limited for {ticker}. Falling back to YFinance.")
            try:
                yf_vendor = YFinanceVendor()
                return yf_vendor.get_options_chain(ticker)
            except Exception as e:
                logger.error(f"Fallback to YFinance options failed for {ticker}: {e}")
                return None

        try:
            contracts = data["results"]
            expirations = sorted(set(c["expiration_date"] for c in contracts))[:3]

            chains = {}
            for exp in expirations:
                exp_contracts = [c for c in contracts if c["expiration_date"] == exp]
                calls = [c for c in exp_contracts if c.get("contract_type") == "call"]
                puts = [c for c in exp_contracts if c.get("contract_type") == "put"]
                chains[exp] = {
                    "calls": pd.DataFrame(calls) if calls else pd.DataFrame(),
                    "puts": pd.DataFrame(puts) if puts else pd.DataFrame(),
                }

            return {"expirations": expirations, "chains": chains}
        except Exception as e:
            logger.error(f"DATA_QUALITY_FAILURE | ticker={ticker} | field=options | reason=polygon_parse_error | detail={e}")
            try:
                yf_vendor = YFinanceVendor()
                return yf_vendor.get_options_chain(ticker)
            except Exception:
                return None


class CachedDataVendor(DataVendorClient):
    """
    Data Vendor wrapper that intercepts get_ohlcv requests, checks cache,
    and only fetches the delta from the last cached date forward.
    """

    def __init__(self, inner_vendor: DataVendorClient):
        self.inner = inner_vendor
        self._memory_cache: Dict[str, Any] = {}
        self._memory_lock = threading.Lock()

    def get_financials(self, ticker: str, period: str = "quarterly") -> Optional[Dict[str, pd.DataFrame]]:
        key = f"financials:{ticker.upper()}:{period}"
        cached = self._get_memory(key)
        if cached is not None:
            logger.info(f"FINANCIALS_MEMORY_CACHE_HIT | ticker={ticker} | period={period}")
            return cached

        data = self.inner.get_financials(ticker, period)
        if data is not None:
            self._set_memory(key, data)
        return data

    def get_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        key = f"info:{ticker.upper()}"
        cached = self._get_memory(key)
        if cached is not None:
            logger.info(f"INFO_MEMORY_CACHE_HIT | ticker={ticker}")
            return cached

        data = self.inner.get_info(ticker)
        if data is not None:
            self._set_memory(key, data)
        return data

    def get_insider_transactions(self, ticker: str) -> Optional[pd.DataFrame]:
        key = f"insider_transactions:{ticker.upper()}"
        cached = self._get_memory(key)
        if cached is not None:
            logger.info(f"INSIDER_MEMORY_CACHE_HIT | ticker={ticker}")
            return cached

        data = self.inner.get_insider_transactions(ticker)
        if data is not None:
            self._set_memory(key, data)
        return data

    def get_options_chain(self, ticker: str) -> Optional[Dict[str, Any]]:
        key = f"options:{ticker.upper()}"
        cached = self._get_memory(key)
        if cached is not None:
            logger.info(f"OPTIONS_MEMORY_CACHE_HIT | ticker={ticker}")
            return cached

        data = self.inner.get_options_chain(ticker)
        if data is not None:
            self._set_memory(key, data)
        return data

    def _get_memory(self, key: str) -> Optional[Any]:
        with self._memory_lock:
            return self._memory_cache.get(key)

    def _set_memory(self, key: str, value: Any):
        with self._memory_lock:
            self._memory_cache[key] = value

    def get_ohlcv(self, ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
        from pipeline.infra.cache import cache
        import datetime

        try:
            start_date = datetime.datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end, "%Y-%m-%d").date()
        except Exception:
            return self.inner.get_ohlcv(ticker, start, end)

        today = datetime.date.today()
        if end_date >= today:
            last_completed = today - datetime.timedelta(days=1)
            while last_completed.weekday() >= 5:
                last_completed -= datetime.timedelta(days=1)
            end_date = min(end_date, last_completed)
            end = end_date.strftime("%Y-%m-%d")

        key = f"ohlcv:{ticker.upper()}:{start}:{end}"
        cached = self._get_memory(key)
        if cached is not None:
            logger.info(f"OHLCV_MEMORY_CACHE_HIT | ticker={ticker} | range={start}_to={end}")
            return cached

        # 1. Fetch whatever we have in cache
        cached_df = cache.get_cached_ohlcv(ticker, start, end)
        latest_cached = cache.get_latest_ohlcv_date(ticker)

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
                # Save newly retrieved delta data to database
                cache.save_ohlcv(ticker, delta_df)
                # Fetch unified sorted dataset
                cached_df = cache.get_cached_ohlcv(ticker, start, end)
        else:
            logger.info(f"OHLCV_CACHE_HIT | ticker={ticker} | range={start}_to={end}")

        if cached_df is not None:
            self._set_memory(key, cached_df)
        return cached_df


def get_data_vendor() -> DataVendorClient:
    """
    Factory function. Returns the configured data vendor wrapped in CachedDataVendor.
    """
    vendor_choice = os.getenv("DATA_VENDOR", "auto").lower()

    if vendor_choice == "polygon":
        try:
            inner = PolygonVendor()
        except DataRetrievalError:
            logger.warning("Polygon API key not found. Falling back to YFinance.")
            inner = YFinanceVendor()
    elif vendor_choice == "yfinance":
        inner = YFinanceVendor()
    else:  # auto
        if os.getenv("POLYGON_API_KEY"):
            try:
                inner = PolygonVendor()
            except DataRetrievalError:
                inner = YFinanceVendor()
        else:
            inner = YFinanceVendor()
            
    return CachedDataVendor(inner)


# Global vendor instance
vendor = get_data_vendor()
