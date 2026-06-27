import json
from typing import Dict, Any
from pipeline.infra.gemini_client import gemini_client

async def run_general_expert(ticker: str, tier1a_json: Dict[str, Any], tier1b_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tier 2 General Expert.
    Merges Quant (Tier 1A) and Narrative (Tier 1B) JSON into a final signal.
    """
    
    system_instruction = """
    You are the lead analyst. Merge the quantitative and qualitative
    reports below into one signal. If they conflict, say so explicitly rather
    than averaging them away. You must provide two distinct signals: 
    a tactical_horizon_30d signal based on technicals and momentum, and 
    a structural_horizon_1y signal based on balance sheet solvency and margins.
    """
    
    prompt = f"""
    [QUANT_REPORT]
    {json.dumps(tier1a_json)}
    
    [NARRATIVE_REPORT]
    {json.dumps(tier1b_json)}
    
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
        return parsed_res.model_dump()
    else:
        print(f"Error parsing General Expert JSON for {ticker}.")
        return {}
