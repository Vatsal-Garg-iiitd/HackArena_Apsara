"""
PostgreSQL-backed cache with proper schema.
Supports separate tables for different data types with cache invalidation policies.
Falls back to SQLite if PostgreSQL is unavailable.
"""

import os
import json
import logging
import time
from typing import Any, Optional
from datetime import date
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CACHE_DIR = ".pipeline_cache"
SQLITE_DB_PATH = os.path.join(CACHE_DIR, "cache.db")


class PostgresCache:
    """PostgreSQL-backed cache with structured tables."""

    def __init__(self, database_url: str):
        import psycopg2
        self.conn = psycopg2.connect(database_url)
        self.conn.autocommit = True
        self._init_tables()

    def _init_tables(self):
        """Create cache tables if they don't exist."""
        with self.conn.cursor() as cur:
            # Generic key-value cache (for LLM outputs, etc.)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_cache (
                    key TEXT PRIMARY KEY,
                    value JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ
                )
            """)

            # OHLCV data cache
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ohlcv_cache (
                    ticker TEXT NOT NULL,
                    trade_date DATE NOT NULL,
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION,
                    volume BIGINT,
                    adjusted_close DOUBLE PRECISION,
                    source TEXT DEFAULT 'polygon',
                    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (ticker, trade_date)
                )
            """)

            # Financial statement cache
            cur.execute("""
                CREATE TABLE IF NOT EXISTS financials_cache (
                    ticker TEXT NOT NULL,
                    period_end DATE NOT NULL,
                    statement_type TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    value DOUBLE PRECISION,
                    source TEXT DEFAULT 'polygon',
                    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (ticker, period_end, statement_type, field_name)
                )
            """)

            # Transcript cache
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transcript_cache (
                    ticker TEXT NOT NULL,
                    event_date DATE NOT NULL,
                    event_type TEXT DEFAULT 'earnings_call',
                    raw_text TEXT,
                    processed_json JSONB,
                    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (ticker, event_date, event_type)
                )
            """)

            # Signal output cache
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signal_cache (
                    ticker TEXT NOT NULL,
                    run_date DATE NOT NULL,
                    tier TEXT NOT NULL,
                    signal_json JSONB,
                    confidence DOUBLE PRECISION,
                    data_quality DOUBLE PRECISION,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (ticker, run_date, tier)
                )
            """)

            # Run history for observability
            cur.execute("""
                CREATE TABLE IF NOT EXISTS run_history (
                    run_id TEXT PRIMARY KEY,
                    started_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    tickers_requested INTEGER,
                    tickers_succeeded INTEGER,
                    tickers_failed INTEGER,
                    summary_json JSONB
                )
            """)

    def get(self, key: str) -> Optional[Any]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT value FROM pipeline_cache WHERE key = %s AND (expires_at IS NULL OR expires_at > NOW())",
                    (key,)
                )
                row = cur.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            logger.error(f"PostgreSQL cache read error for key {key}: {e}")
        return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        try:
            value_json = json.dumps(value)
            with self.conn.cursor() as cur:
                if ttl_seconds:
                    cur.execute(
                        """INSERT INTO pipeline_cache (key, value, expires_at) 
                           VALUES (%s, %s::jsonb, NOW() + INTERVAL '%s seconds')
                           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, 
                           expires_at = EXCLUDED.expires_at, created_at = NOW()""",
                        (key, value_json, ttl_seconds)
                    )
                else:
                    cur.execute(
                        """INSERT INTO pipeline_cache (key, value) 
                           VALUES (%s, %s::jsonb)
                           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, created_at = NOW()""",
                        (key, value_json)
                    )
        except Exception as e:
            logger.error(f"PostgreSQL cache write error for key {key}: {e}")

    def save_run_history(self, run_id: str, summary: dict):
        """Save pipeline run history for observability."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO run_history (run_id, completed_at, tickers_requested, 
                       tickers_succeeded, tickers_failed, summary_json) 
                       VALUES (%s, NOW(), %s, %s, %s, %s::jsonb)
                       ON CONFLICT (run_id) DO UPDATE SET completed_at = NOW(), 
                       summary_json = EXCLUDED.summary_json""",
                    (run_id, 
                     summary.get("tickers", {}).get("requested", 0),
                     summary.get("tickers", {}).get("succeeded", 0),
                     summary.get("tickers", {}).get("failed", 0),
                     json.dumps(summary))
                )
        except Exception as e:
            logger.error(f"Error saving run history: {e}")

    def get_cached_ohlcv(self, ticker: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """SELECT trade_date, open, high, low, close, volume FROM ohlcv_cache 
                       WHERE ticker = %s AND trade_date >= %s AND trade_date <= %s 
                       ORDER BY trade_date ASC""",
                    (ticker, start_date, end_date)
                )
                rows = cur.fetchall()
                if rows:
                    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
                    df["Date"] = pd.to_datetime(df["Date"])
                    df.set_index("Date", inplace=True)
                    return df
        except Exception as e:
            logger.error(f"Error reading OHLCV cache for {ticker}: {e}")
        return None

    def get_latest_ohlcv_date(self, ticker: str) -> Optional[date]:
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT MAX(trade_date) FROM ohlcv_cache WHERE ticker = %s", (ticker,))
                row = cur.fetchone()
                if row and row[0]:
                    return row[0]
        except Exception as e:
            logger.error(f"Error fetching max trade date for {ticker}: {e}")
        return None

    def save_ohlcv(self, ticker: str, df: pd.DataFrame):
        try:
            with self.conn.cursor() as cur:
                for idx, row in df.iterrows():
                    trade_date = idx.date() if hasattr(idx, 'date') else idx
                    cur.execute(
                        """INSERT INTO ohlcv_cache (ticker, trade_date, open, high, low, close, volume) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (ticker, trade_date) DO UPDATE SET 
                           open = EXCLUDED.open, high = EXCLUDED.high, 
                           low = EXCLUDED.low, close = EXCLUDED.close, volume = EXCLUDED.volume""",
                        (ticker, trade_date, row["Open"], row["High"], row["Low"], row["Close"], int(row["Volume"]))
                    )
        except Exception as e:
            logger.error(f"Error saving OHLCV to cache for {ticker}: {e}")


class SQLiteFallbackCache:
    """SQLite fallback when PostgreSQL is unavailable."""

    def __init__(self):
        import sqlite3
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
        self.conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv_cache (
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                PRIMARY KEY (ticker, trade_date)
            )
        """)
        self.conn.commit()

    def get(self, key: str) -> Optional[Any]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM cache WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return None
        return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        try:
            value_str = json.dumps(value)
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)",
                (key, value_str)
            )
            self.conn.commit()
        except Exception as e:
            logger.error(f"SQLite cache write error for key {key}: {e}")

    def save_run_history(self, run_id: str, summary: dict):
        """No-op for SQLite fallback."""
        pass

    def get_cached_ohlcv(self, ticker: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        try:
            import pandas as pd
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT trade_date, open, high, low, close, volume FROM ohlcv_cache 
                   WHERE ticker = ? AND trade_date >= ? AND trade_date <= ? 
                   ORDER BY trade_date ASC""",
                (ticker, start_date, end_date)
            )
            rows = cursor.fetchall()
            if rows:
                df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
                df["Date"] = pd.to_datetime(df["Date"])
                df.set_index("Date", inplace=True)
                return df
        except Exception as e:
            logger.error(f"Error reading SQLite OHLCV cache for {ticker}: {e}")
        return None

    def get_latest_ohlcv_date(self, ticker: str):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT MAX(trade_date) FROM ohlcv_cache WHERE ticker = ?", (ticker,))
            row = cursor.fetchone()
            if row and row[0]:
                import datetime
                # SQLite stores dates as strings, convert to date object
                return datetime.datetime.strptime(row[0], "%Y-%m-%d").date()
        except Exception as e:
            logger.error(f"Error fetching max trade date from SQLite for {ticker}: {e}")
        return None

    def save_ohlcv(self, ticker: str, df: pd.DataFrame):
        try:
            cursor = self.conn.cursor()
            for idx, row in df.iterrows():
                trade_date = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)
                cursor.execute(
                    """INSERT OR REPLACE INTO ohlcv_cache (ticker, trade_date, open, high, low, close, volume) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (ticker, trade_date, row["Open"], row["High"], row["Low"], row["Close"], int(row["Volume"]))
                )
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error saving OHLCV to SQLite cache for {ticker}: {e}")


def create_cache():
    """
    Create the appropriate cache backend.
    Uses PostgreSQL if DATABASE_URL is configured, otherwise falls back to SQLite.
    """
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        try:
            pg_cache = PostgresCache(database_url)
            logger.info("Using PostgreSQL cache backend")
            return pg_cache
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed ({e}). Falling back to SQLite.")

    logger.info("Using SQLite cache backend (fallback)")
    return SQLiteFallbackCache()


# Global instance
cache = create_cache()
