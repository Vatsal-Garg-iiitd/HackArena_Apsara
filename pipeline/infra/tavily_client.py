"""
Tavily News Client.
Fetches real-time news for a ticker using the Tavily Search API.
Falls back to a basic mock if TAVILY_API_KEY is not configured.
"""

import os
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def fetch_recent_news(ticker: str, max_results: int = 5) -> Dict:
    """
    Fetch recent news articles for a ticker using Tavily and return structured
    data suitable for API responses.
    """
    api_key = os.getenv("TAVILY_API_KEY", "")

    if not api_key:
        message = f"No real-time news data available for {ticker}. TAVILY_API_KEY not configured."
        logger.warning(message)
        return {
            "ticker": ticker.upper(),
            "provider": "tavily",
            "api_key_configured": False,
            "results": [],
            "formatted": f"[{message}]",
            "error": None,
        }

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=f"{ticker} stock latest news financial analysis",
            search_depth="basic",
            max_results=max_results,
            time_range="week",
            include_domains=[
                "bloomberg.com", "reuters.com", "wsj.com",
                "cnbc.com", "marketwatch.com", "seekingalpha.com",
                "finance.yahoo.com", "barrons.com", "ft.com",
                "thestreet.com", "investopedia.com",
            ],
        )

        raw_results = response.get("results", [])
        results = []
        snippets = []

        for item in raw_results:
            title = item.get("title", "")
            url = item.get("url", "")
            content = item.get("content", "")
            score = item.get("score")

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

            results.append({
                "title": title,
                "url": url,
                "publisher": publisher,
                "content": content,
                "snippet": snippet,
                "score": score,
            })
            snippets.append(f"- [{publisher}] {title}\n  {snippet}")

        formatted = "\n".join(snippets) if snippets else f"[No recent news found for {ticker} in the past week.]"
        logger.info(f"Tavily returned {len(results)} news results for {ticker}.")
        return {
            "ticker": ticker.upper(),
            "provider": "tavily",
            "api_key_configured": True,
            "results": results,
            "formatted": formatted,
            "error": None,
        }

    except ImportError:
        message = "tavily-python package not installed. Run: pip install tavily-python"
        logger.error(message)
        return {
            "ticker": ticker.upper(),
            "provider": "tavily",
            "api_key_configured": True,
            "results": [],
            "formatted": f"[{message}]",
            "error": message,
        }
    except Exception as e:
        message = f"Tavily API error for {ticker}: {e}"
        logger.error(message)
        return {
            "ticker": ticker.upper(),
            "provider": "tavily",
            "api_key_configured": True,
            "results": [],
            "formatted": f"[News fetch failed for {ticker}: {e}]",
            "error": str(e),
        }


def get_recent_news(ticker: str, max_results: int = 5) -> str:
    """
    Fetch recent news articles for a ticker using Tavily Search API.
    Returns formatted news snippets ready for LLM consumption.
    Falls back to empty string if Tavily is unavailable.
    """
    return fetch_recent_news(ticker, max_results=max_results)["formatted"]
