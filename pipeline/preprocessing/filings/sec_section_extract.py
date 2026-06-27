"""
SEC EDGAR 10-K Section Extractor.
Replaces the stub implementation with real EDGAR API integration.
Extracts Item 1A (Risk Factors) and Item 7 (MD&A) from actual filings.
"""

import logging
from typing import Dict, Optional
from pipeline.infra.edgar_client import edgar_client

logger = logging.getLogger(__name__)


def extract_10k_sections(ticker: str) -> Dict[str, Optional[str]]:
    """
    Extract Item 1A (Risk Factors) and Item 7 (MD&A) from the latest 10-K filing.
    Uses the EDGAR client to fetch and parse real SEC filings.
    Falls back to a structured message if filing is unavailable.
    """
    try:
        sections = edgar_client.extract_10k_sections(ticker)

        item_1a = sections.get("item_1a_risk_factors")
        item_7 = sections.get("item_7_mda")

        if item_1a is None and item_7 is None:
            logger.warning(f"No 10-K sections found for {ticker} via EDGAR. Using unavailable notice.")
            return {
                "item_1a_risk_factors": f"[10-K Risk Factors section not available for {ticker} from EDGAR]",
                "item_7_mda": f"[10-K MD&A section not available for {ticker} from EDGAR]",
            }

        return {
            "item_1a_risk_factors": item_1a if item_1a else f"[Item 1A not parsed for {ticker}]",
            "item_7_mda": item_7 if item_7 else f"[Item 7 not parsed for {ticker}]",
        }

    except Exception as e:
        logger.error(f"Error extracting 10-K for {ticker}: {e}")
        return {
            "item_1a_risk_factors": f"[Error fetching 10-K for {ticker}: {e}]",
            "item_7_mda": f"[Error fetching 10-K for {ticker}: {e}]",
        }
