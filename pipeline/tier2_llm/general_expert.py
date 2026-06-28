import json
import logging
from typing import Dict, Any, Optional
from pipeline.infra.gemini_client import gemini_client

logger = logging.getLogger(__name__)


async def run_general_expert(
    ticker: str,
    tier1a_json: Dict[str, Any],
    tier1b_json: Dict[str, Any],
    tier1c_json: Optional[Dict[str, Any]] = None,
    macro_regime: Optional[str] = None,
    consistency_flags: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Tier 2 General Expert.
    Merges Quant (Tier 1A) and Narrative (Tier 1B) JSON into a final signal.
    Now includes uncertainty quantification and macro regime adjustment.
    """

    consistency_context = ""
    if consistency_flags:
        consistency_context = (
            "\n\nNOTE: The following consistency issues were detected in the upstream "
            "analysis. Account for these when forming your assessment:\n" +
            "\n".join(f"- {flag}" for flag in consistency_flags)
        )

    macro_context = ""
    if macro_regime:
        macro_context = f"\n\n[MACRO_REGIME]\n{macro_regime}"
        macro_context += (
            "\nIn a bearish macro regime, apply a 15% confidence penalty to all "
            "bullish tactical signals unless they are driven by company-specific "
            "catalysts independent of macro direction."
        )

    system_instruction = f"""
    You are the lead analyst. Merge the quantitative and qualitative
    reports below into one signal. Tier 1C is a deterministic raw OHLCV
    analysis from yfinance; use it primarily for tactical trend, volatility,
    volume-confirmation, and drawdown context. If reports conflict, say so
    explicitly rather than averaging them away. You must provide two distinct signals:
    a tactical_horizon_30d signal based on technicals and momentum, and 
    a structural_horizon_1y signal based on balance sheet solvency and margins.
    
    CRITICAL: For EACH signal (tactical and structural), you MUST provide:
    1. direction: "bullish", "bearish", or "neutral"
    2. confidence: a float from 0.0 to 1.0 where 1.0 means all evidence strongly 
       supports this conclusion with no contradictions
    3. corroborating_signals: at least 3 specific data points supporting your conclusion
    4. contradicting_signals: any data points contradicting your conclusion, even if 
       the overall conclusion remains the same
    5. data_quality_score: 0.0 if critical data was missing, 1.0 if all data was clean
    
    A signal with confidence below 0.5 should be flagged for human review.
    A signal with data_quality_score below 0.7 should include a data quality warning.
    {consistency_context}
    """

    prompt = f"""
    [QUANT_REPORT]
    {json.dumps(tier1a_json)}
    
    [NARRATIVE_REPORT]
    {json.dumps(tier1b_json)}

    [RAW_OHLCV_REPORT]
    {json.dumps(tier1c_json or {})}
    {macro_context}
    
    Provide signals for {ticker}.
    """

    from pipeline.schemas.llm_schemas import GeneralExpertOutput
    parsed_res = await gemini_client.generate_json(
        model_name="gemini-2.5-flash",
        system_instruction=system_instruction,
        prompt=prompt,
        schema=GeneralExpertOutput
    )

    if parsed_res:
        result = parsed_res.model_dump()
        # Inject consistency flags into the result
        if consistency_flags:
            result["consistency_flags"] = consistency_flags
        if tier1c_json:
            result["tier1c_ohlcv_analysis"] = tier1c_json
        return result
    else:
        logger.error(f"Error parsing General Expert JSON for {ticker}.")
        return {}
