import json
from typing import Dict, Any
from pipeline.infra.gemini_client import gemini_client
from pipeline.preprocessing.earnings_call import process_latest_earnings_call
from pipeline.preprocessing.filings.sec_section_extract import extract_10k_sections

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
    """
    
    news_snippets = get_recent_news(ticker)
    earnings_preprocessed = process_latest_earnings_call(ticker)
    sec_sections = extract_10k_sections(ticker)
    
    system_instruction = f"""
    You are a qualitative research analyst. You have independent text sections 
    for {ticker}. Reason about each section independently using only its own data. 
    """
    
    prompt = f"""
    [NEWS]
    {news_snippets}
    
    [EARNINGS_CALL]
    {json.dumps(earnings_preprocessed)}
    
    [FILING_OUTLOOK]
    {sec_sections.get("item_1a_risk_factors", "")}
    {sec_sections.get("item_7_mda", "")}
    
    [COMPETITIVE]
    # For this prototype, competitor info is inferred from news and filings.
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
        print(f"Error parsing Narrative Synthesizer JSON for {ticker}.")
        return {}
