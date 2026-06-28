import json
import logging
from typing import Dict, Any
from pipeline.infra.gemini_client import gemini_client
from pipeline.infra.tavily_client import get_recent_news
from pipeline.preprocessing.earnings_call import process_latest_earnings_call

logger = logging.getLogger(__name__)


async def run_narrative_synthesizer(ticker: str) -> Dict[str, Any]:
    """
    Tier 1B Synthesizer. Runs on a SINGLE ticker using gemini-2.5-flash.
    Should be cached heavily, only run on new earnings transcripts.
    """

    news_snippets = get_recent_news(ticker)
    earnings_preprocessed = process_latest_earnings_call(ticker)

    system_instruction = f"""
    You are a qualitative research analyst. You have independent text sections 
    for {ticker}. Reason about each section independently using only its own data. 
    
    IMPORTANT: For each assessment you make, you MUST provide:
    1. A confidence score from 0.0 to 1.0.
    2. If analyzing earnings calls, note:
       - Whether management hedged or deflected on any questions
       - What analyst questions revealed about market concerns
       - Whether tone shifted between prepared remarks and Q&A
    
    If a data section shows as unavailable or contains placeholder text, 
    reduce your confidence for that assessment significantly and note the data gap.
    """

    prompt = f"""
    [NEWS]
    {news_snippets}
    
    [EARNINGS_CALL]
    {json.dumps(earnings_preprocessed) if earnings_preprocessed else "No earnings call data available."}
    
    [COMPETITIVE]
    # Competitive context is inferred from news and earnings calls.
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
