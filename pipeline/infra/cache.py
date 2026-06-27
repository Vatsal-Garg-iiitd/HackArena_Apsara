import os
import json
import sqlite3
from typing import Any, Optional

CACHE_DIR = ".pipeline_cache"
DB_PATH = os.path.join(CACHE_DIR, "cache.db")

class SQLiteCache:
    def __init__(self):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR)
            
        # Initialize SQLite DB
        # check_same_thread=False is needed if we use this across async tasks,
        # though we should be careful. A simple locking mechanism is provided natively by SQLite.
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
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

    def set(self, key: str, value: Any):
        cursor = self.conn.cursor()
        try:
            value_str = json.dumps(value)
            cursor.execute(
                "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)",
                (key, value_str)
            )
            self.conn.commit()
        except Exception as e:
            print(f"Cache write error for key {key}: {e}")

# Global instance
cache = SQLiteCache()
