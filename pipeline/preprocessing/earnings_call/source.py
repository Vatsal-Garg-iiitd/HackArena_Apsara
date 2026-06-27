"""
Earnings Call Transcript Sources.
Provides a TranscriptSource interface with multiple concrete implementations:
- MockTranscriptSource (testing)
- FinnhubTranscriptSource (requires API key)
- Edgar8KTranscriptSource (free, uses SEC EDGAR 8-K filings)
"""

import os
import re
import logging
import requests
from typing import Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class TranscriptSource(ABC):
    @abstractmethod
    def fetch_latest_transcript(self, ticker: str) -> Optional[str]:
        pass


class MockTranscriptSource(TranscriptSource):
    """A mock source for testing preprocessing without burning API keys."""
    def fetch_latest_transcript(self, ticker: str) -> Optional[str]:
        return """
Operator: Good afternoon, and welcome to the Q1 2026 Earnings Conference Call. I will now turn the call over to Investor Relations.

Jane Doe - Investor Relations:
Thank you, operator. Welcome everyone. Before we begin, please note that this call contains forward-looking statements that are subject to risks and uncertainties. Actual results may differ materially. Now, I'll turn it over to our CEO, John Smith.

John Smith - Chief Executive Officer:
Thank you, Jane. We had a strong quarter with record margins. Our outlook remains positive despite macro headwinds. I'll hand it to our CFO.

Alice Johnson - Chief Financial Officer:
Thanks, John. Revenue grew 15% year over year. We are raising our full-year guidance based on strong demand.

Operator: We will now begin the question-and-answer session. First question comes from Bob at Analyst Firm.

Bob - Analyst:
Can you talk more about the margin expansion?

Alice Johnson (CFO):
Yes, our margin expansion was primarily driven by lower opex and pricing discipline.
"""


class FinnhubTranscriptSource(TranscriptSource):
    def __init__(self):
        self.api_key = os.getenv("FINNHUB_API_KEY")

    def fetch_latest_transcript(self, ticker: str) -> Optional[str]:
        if not self.api_key:
            logger.info("No Finnhub API key found.")
            return None
        try:
            url = f"https://finnhub.io/api/v1/stock/transcripts?symbol={ticker}&token={self.api_key}"
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    raw_text = ""
                    for item in data[0].get('transcript', []):
                        raw_text += f"{item.get('name', 'Unknown')}: {item.get('speech', '')}\n\n"
                    return raw_text
        except Exception as e:
            logger.error(f"Error fetching from Finnhub: {e}")
        return None


class Edgar8KTranscriptSource(TranscriptSource):
    """
    Fetches earnings call transcripts from SEC EDGAR 8-K filings.
    Many companies file transcripts as exhibits to 8-K filings within 24-72 hours.
    Free, no API key required. SEC mandates a proper User-Agent header.
    """

    EDGAR_HEADERS = {
        "User-Agent": "HackArena Research Pipeline contact@example.com",
        "Accept-Encoding": "gzip, deflate",
    }

    def _get_cik(self, ticker: str) -> Optional[str]:
        """Look up CIK from ticker."""
        try:
            url = "https://www.sec.gov/files/company_tickers.json"
            response = requests.get(url, headers=self.EDGAR_HEADERS, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for entry in data.values():
                    if entry.get("ticker", "").upper() == ticker.upper():
                        return str(entry["cik_str"]).zfill(10)
        except Exception as e:
            logger.warning(f"CIK lookup failed for {ticker}: {e}")
        return None

    def fetch_latest_transcript(self, ticker: str) -> Optional[str]:
        """
        Search EDGAR for recent 8-K filings that contain earnings call transcripts.
        """
        try:
            # Search for 8-K filings mentioning "earnings call" for this company
            url = "https://efts.sec.gov/LATEST/search-index"
            params = {
                "q": f'"{ticker}" "earnings call"',
                "forms": "8-K",
                "dateRange": "custom",
                "startdt": "2024-01-01",
            }
            response = requests.get(url, params=params, headers=self.EDGAR_HEADERS, timeout=15)

            if response.status_code != 200:
                logger.warning(f"EDGAR 8-K search returned {response.status_code}")
                return None

            data = response.json()
            hits = data.get("hits", {}).get("hits", [])

            if not hits:
                logger.info(f"No 8-K earnings transcripts found for {ticker}")
                return None

            # Get the first (most recent) hit
            first_hit = hits[0]
            source = first_hit.get("_source", {})
            file_url = source.get("file_url")

            if not file_url:
                return None

            # Fetch the actual filing
            filing_url = f"https://www.sec.gov{file_url}" if file_url.startswith("/") else file_url
            filing_response = requests.get(filing_url, headers=self.EDGAR_HEADERS, timeout=30)

            if filing_response.status_code == 200:
                # Extract text content (rough extraction)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(filing_response.text, "lxml")
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator="\n")

                # Clean up
                lines = [line.strip() for line in text.split("\n") if line.strip()]
                cleaned = "\n".join(lines)

                if len(cleaned) > 500:  # Sanity check
                    return cleaned

        except Exception as e:
            logger.error(f"Error fetching 8-K transcript for {ticker}: {e}")

        return None


def get_transcript_source() -> TranscriptSource:
    """
    Factory: selects the best available transcript source.
    Priority: Finnhub (if key available) > EDGAR 8-K > Mock.
    """
    source_pref = os.getenv("TRANSCRIPT_SOURCE", "auto").lower()

    if source_pref == "mock":
        return MockTranscriptSource()
    elif source_pref == "finnhub":
        return FinnhubTranscriptSource()
    elif source_pref == "edgar":
        return Edgar8KTranscriptSource()
    else:  # auto
        if os.getenv("FINNHUB_API_KEY"):
            return FinnhubTranscriptSource()
        # Try EDGAR 8-K source (free, no key needed)
        return Edgar8KTranscriptSource()
