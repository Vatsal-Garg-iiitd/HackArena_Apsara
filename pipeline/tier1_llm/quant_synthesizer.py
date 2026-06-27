import json
from typing import List, Dict, Any
from pipeline.schemas.tier0 import Tier0Output
from pipeline.infra.gemini_client import gemini_client
from pipeline.schemas.llm_schemas import QuantSynthesizerBatch

def get_mock_macro() -> Dict[str, Any]:
    """Mock FRED macro data."""
    return {
        "10yr_yield": 4.12,
        "yield_curve": "inverted",
        "inflation_cpi_yoy": 3.1,
        "fed_funds_rate": 5.25
    }

async def run_quant_synthesizer(tier0_outputs: List[Tier0Output]) -> List[Dict[str, Any]]:
    """
    Tier 1A Synthesizer. Runs on batch of tickers using gemini-2.5-flash.
    """
    if not tier0_outputs:
        return []
        
    macro = get_mock_macro()
    
    prompt = ""
    for out in tier0_outputs:
        prompt += f"\nFor ticker {out.ticker}:\n"
        prompt += f"[SOLVENCY & LIQUIDITY] {out.solvency.model_dump_json()}\n"
        prompt += f"[EFFICIENCY & TURNOVER] {out.efficiency.model_dump_json()}\n"
        prompt += f"[PROFITABILITY] {out.profitability.model_dump_json()}\n"
        prompt += f"[INVESTOR_BEHAVIOR] {out.investor_behavior.model_dump_json()}\n"
        prompt += f"[TECHNICAL] {out.technical.model_dump_json()}\n"
        if out.normalized_metrics:
            prompt += f"[NORMALIZED_VS_PEERS] {out.normalized_metrics.model_dump_json()}\n"
        prompt += f"[MACRO_CONTEXT] {json.dumps(macro)}\n"
        
    system_instruction = """
    You are a quantitative analyst. For each ticker below, you have independent data sections.
    Reason about EACH section using ONLY the data in that section — do not let one section's 
    data influence another's interpretation.
    """
    
    parsed_batch = await gemini_client.generate_json(
        model_name="gemini-2.5-flash",
        system_instruction=system_instruction,
        prompt=prompt,
        schema=QuantSynthesizerBatch
    )
    
    if parsed_batch and hasattr(parsed_batch, "results"):
        return [res.model_dump(by_alias=True) for res in parsed_batch.results]
    else:
        print(f"Error parsing Quant Synthesizer JSON. Raw output: {parsed_batch}")
        return []
