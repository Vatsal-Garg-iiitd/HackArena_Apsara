"""
Tavily news client for API and future narrative-context use.
"""

import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def fetch_recent_news(ticker: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Fetch recent stock news from Tavily and return structured API-safe data.
    """
    symbol = ticker.upper()
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        message = f"No real-time news data available for {symbol}. TAVILY_API_KEY not configured."
        logger.warning(message)
        return {
            "ticker": symbol,
            "provider": "tavily",
            "api_key_configured": False,
            "results": [],
            "formatted": f"[{message}]",
            "error": None,
        }

    try:
        from tavily import TavilyClient
    except ImportError:
        message = "tavily-python package not installed."
        logger.error(message)
        return {
            "ticker": symbol,
            "provider": "tavily",
            "api_key_configured": True,
            "results": [],
            "formatted": f"[{message}]",
            "error": message,
        }

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=f"{symbol} stock latest news financial analysis",
            search_depth="basic",
            max_results=max_results,
            time_range="week",
            include_domains=[
                "bloomberg.com",
                "reuters.com",
                "wsj.com",
                "cnbc.com",
                "marketwatch.com",
                "seekingalpha.com",
                "finance.yahoo.com",
                "barrons.com",
                "ft.com",
                "thestreet.com",
                "investopedia.com",
            ],
        )

        results: List[Dict[str, Any]] = []
        formatted_items = []
        for item in response.get("results", []):
            title = item.get("title", "")
            url = item.get("url", "")
            content = item.get("content", "")
            publisher = "Unknown"

            if url:
                try:
                    from urllib.parse import urlparse

                    domain = urlparse(url).netloc.replace("www.", "")
                    publisher = domain.split(".")[0].capitalize()
                except Exception:
                    pass

            snippet = content[:250].strip()
            if len(content) > 250:
                snippet += "..."

            result = {
                "title": title,
                "url": url,
                "publisher": publisher,
                "content": content,
                "snippet": snippet,
                "score": item.get("score"),
            }
            results.append(result)
            formatted_items.append(f"- [{publisher}] {title}\n  {snippet}")

        formatted = "\n".join(formatted_items) if formatted_items else f"[No recent news found for {symbol}.]"
        return {
            "ticker": symbol,
            "provider": "tavily",
            "api_key_configured": True,
            "results": results,
            "formatted": formatted,
            "error": None,
        }
    except Exception as e:
        logger.error(f"Tavily API error for {symbol}: {e}")
        return {
            "ticker": symbol,
            "provider": "tavily",
            "api_key_configured": True,
            "results": [],
            "formatted": f"[News fetch failed for {symbol}: {e}]",
            "error": str(e),
        }


def get_recent_news(ticker: str, max_results: int = 5) -> str:
    return fetch_recent_news(ticker, max_results=max_results)["formatted"]
