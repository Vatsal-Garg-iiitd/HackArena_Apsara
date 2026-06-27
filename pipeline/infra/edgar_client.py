"""
SEC EDGAR Client.
Provides structured access to EDGAR APIs:
- CIK lookup from ticker
- XBRL financial facts (companyfacts API)
- Full-text filing search
- 10-K section extraction (Item 1A, Item 7)
"""

import re
import logging
import warnings
import requests
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning

# Suppress BeautifulSoup XML-parsed-as-HTML warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)

# SEC mandates a proper User-Agent identifying the requester
EDGAR_HEADERS = {
    "User-Agent": "HackArena Research Pipeline contact@example.com",
    "Accept-Encoding": "gzip, deflate",
}

# CIK cache
_cik_cache: Dict[str, str] = {}
_tickers_json_cache: Optional[Dict] = None


class EdgarClient:
    """Client for SEC EDGAR APIs."""

    def get_cik(self, ticker: str) -> Optional[str]:
        """Look up a company's CIK (Central Index Key) from its ticker symbol."""
        global _cik_cache, _tickers_json_cache

        ticker = ticker.upper()
        if ticker in _cik_cache:
            return _cik_cache[ticker]

        try:
            if _tickers_json_cache is None:
                url = "https://www.sec.gov/files/company_tickers.json"
                response = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
                if response.status_code == 200:
                    _tickers_json_cache = response.json()
                else:
                    return None

            for entry in _tickers_json_cache.values():
                if entry.get("ticker", "").upper() == ticker:
                    cik = str(entry["cik_str"]).zfill(10)
                    _cik_cache[ticker] = cik
                    return cik
        except Exception as e:
            logger.error(f"CIK lookup failed for {ticker}: {e}")
        return None

    def get_company_facts(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetch all structured XBRL financial facts for a company from EDGAR.
        Endpoint: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
        Returns every financial fact the company has ever reported in XBRL format.
        """
        cik = self.get_cik(ticker)
        if cik is None:
            return None

        try:
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            response = requests.get(url, headers=EDGAR_HEADERS, timeout=30)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"EDGAR companyfacts returned {response.status_code} for {ticker}")
                return None
        except Exception as e:
            logger.error(f"Error fetching company facts for {ticker}: {e}")
            return None

    def search_filings(
        self, query: str, forms: str = "10-K",
        start_date: str = "2023-01-01", limit: int = 5
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Full-text search across EDGAR filings.
        Endpoint: https://efts.sec.gov/LATEST/search-index
        """
        try:
            url = "https://efts.sec.gov/LATEST/search-index"
            params = {
                "q": query,
                "forms": forms,
                "dateRange": "custom",
                "startdt": start_date,
            }
            response = requests.get(url, params=params, headers=EDGAR_HEADERS, timeout=30)
            if response.status_code == 200:
                data = response.json()
                hits = data.get("hits", {}).get("hits", [])
                results = []
                for hit in hits[:limit]:
                    source = hit.get("_source", {})
                    results.append({
                        "accession_number": source.get("file_num"),
                        "form_type": source.get("form_type"),
                        "filing_date": source.get("file_date"),
                        "company_name": source.get("display_names", [""])[0] if source.get("display_names") else "",
                    })
                return results
            return None
        except Exception as e:
            logger.error(f"EDGAR search failed for query '{query}': {e}")
            return None

    def get_latest_10k_url(self, ticker: str) -> Optional[str]:
        """Find the URL of the latest 10-K filing for a ticker."""
        cik = self.get_cik(ticker)
        if cik is None:
            return None

        try:
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            response = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
            if response.status_code != 200:
                return None

            data = response.json()
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accessions = recent.get("accessionNumber", [])
            primary_docs = recent.get("primaryDocument", [])

            for i, form in enumerate(forms):
                if form == "10-K":
                    accession = accessions[i].replace("-", "")
                    doc = primary_docs[i]
                    return f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{accession}/{doc}"

            return None
        except Exception as e:
            logger.error(f"Error finding 10-K for {ticker}: {e}")
            return None

    def extract_10k_sections(self, ticker: str) -> Dict[str, Optional[str]]:
        """
        Extract Item 1A (Risk Factors) and Item 7 (MD&A) from the latest 10-K.
        Uses BeautifulSoup to parse the HTML filing and find section headers.
        """
        filing_url = self.get_latest_10k_url(ticker)
        if filing_url is None:
            logger.info(f"No 10-K URL found for {ticker}")
            return {"item_1a_risk_factors": None, "item_7_mda": None}

        try:
            response = requests.get(filing_url, headers=EDGAR_HEADERS, timeout=30)
            if response.status_code != 200:
                return {"item_1a_risk_factors": None, "item_7_mda": None}

            soup = BeautifulSoup(response.text, "lxml")

            # Remove scripts and styles
            for tag in soup(["script", "style"]):
                tag.decompose()

            text = soup.get_text(separator="\n")

            # Extract Item 1A: Risk Factors
            item_1a = self._extract_section(text, r"Item\s*1A\.?\s*Risk\s*Factors", r"Item\s*1B|Item\s*2\.")
            # Extract Item 7: MD&A
            item_7 = self._extract_section(text, r"Item\s*7\.?\s*Management", r"Item\s*7A|Item\s*8\.")

            # Truncate to reasonable sizes (avoid feeding entire sections to LLM)
            max_chars = 8000
            if item_1a and len(item_1a) > max_chars:
                item_1a = item_1a[:max_chars] + "\n[... truncated for token budget ...]"
            if item_7 and len(item_7) > max_chars:
                item_7 = item_7[:max_chars] + "\n[... truncated for token budget ...]"

            return {
                "item_1a_risk_factors": item_1a,
                "item_7_mda": item_7,
            }

        except Exception as e:
            logger.error(f"Error extracting 10-K sections for {ticker}: {e}")
            return {"item_1a_risk_factors": None, "item_7_mda": None}

    @staticmethod
    def _extract_section(text: str, start_pattern: str, end_pattern: str) -> Optional[str]:
        """Extract text between two regex-matched section headers."""
        try:
            start_match = re.search(start_pattern, text, re.IGNORECASE)
            if not start_match:
                return None

            remaining = text[start_match.start():]
            end_match = re.search(end_pattern, remaining[100:], re.IGNORECASE)  # Skip at least 100 chars

            if end_match:
                section = remaining[:100 + end_match.start()]
            else:
                # Take a reasonable chunk if end marker not found
                section = remaining[:8000]

            # Clean up whitespace
            lines = [line.strip() for line in section.split("\n") if line.strip()]
            return "\n".join(lines)
        except Exception:
            return None


# Global instance
edgar_client = EdgarClient()
