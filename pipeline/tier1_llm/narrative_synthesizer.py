import json
import logging
from typing import Dict, Any
from pipeline.infra.gemini_client import gemini_client
from pipeline.preprocessing.earnings_call import process_latest_earnings_call
from pipeline.preprocessing.filings.sec_section_extract import extract_10k_sections

logger = logging.getLogger(__name__)


def get_recent_news(ticker: str) -> str:
    """Mock fetching recent news titles/snippets."""
    mock_news = [
        {"publisher": "Bloomberg", "title": f"{ticker} announces new product line, defying sector slump."},
        {"publisher": "Reuters", "title": f"Analysts wary of {ticker}'s international exposure amid tariffs."},
        {"publisher": "WSJ", "title": f"Inside {ticker}'s aggressive cost-cutting measures."}
    ]
    snippets = []
    for item in mock_news:
        publisher = item.get("publisher", "Unknown")
        title = item.get("title", "")
        snippets.append(f"- [{publisher}] {title}")
    return "\n".join(snippets)


async def run_narrative_synthesizer(ticker: str) -> Dict[str, Any]:
    """
    Tier 1B Synthesizer. Runs on a SINGLE ticker using gemini-2.5-flash.
    Should be cached heavily, only run on new earnings/filings.
    Now includes structured QA extraction and uncertainty quantification.
    """

    news_snippets = get_recent_news(ticker)
    earnings_preprocessed = process_latest_earnings_call(ticker)
    sec_sections = extract_10k_sections(ticker)

    system_instruction = f"""
    You are a qualitative research analyst. You have independent text sections 
    for {ticker}. Reason about each section independently using only its own data. 
    
    IMPORTANT: For each assessment you make, you MUST provide:
    1. A confidence score from 0.0 to 1.0.
    2. If analyzing earnings calls, note:
       - Whether management hedged or deflected on any questions
       - What analyst questions revealed about market concerns
       - Whether tone shifted between prepared remarks and Q&A
    3. For filing outlook, note any NEW risks not present in prior filings.
    
    If a data section shows as unavailable or contains placeholder text, 
    reduce your confidence for that assessment significantly and note the data gap.
    """

    prompt = f"""
    [NEWS]
    {news_snippets}
    
    [EARNINGS_CALL]
    {json.dumps(earnings_preprocessed) if earnings_preprocessed else "No earnings call data available."}
    
    [FILING_OUTLOOK]
    Risk Factors: {sec_sections.get("item_1a_risk_factors", "Not available")}
    MD&A: {sec_sections.get("item_7_mda", "Not available")}
    
    [COMPETITIVE]
    # Competitive context is inferred from news and filings.
    """

    from pipeline.schemas.llm_schemas import NarrativeSynthesizerOutput
    parsed_res = await gemini_client.generate_json(
        model_name="gemini-2.5-flash",
        system_instruction=system_instruction,
        prompt=prompt,
        schema=NarrativeSynthesizerOutput
    )

    if parsed_res:
        return parsed_res.model_dump()
    else:
        logger.error(f"Error parsing Narrative Synthesizer JSON for {ticker}.")
        return {}
