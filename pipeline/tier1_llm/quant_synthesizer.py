import json
import logging
from typing import List, Dict, Any
from pipeline.schemas.tier0 import Tier0Output
from pipeline.infra.gemini_client import gemini_client
from pipeline.schemas.llm_schemas import QuantSynthesizerBatch

logger = logging.getLogger(__name__)


async def run_quant_synthesizer(tier0_outputs: List[Tier0Output]) -> List[Dict[str, Any]]:
    """
    Tier 1A Synthesizer. Runs on batch of tickers using gemini-2.5-flash.
    Now includes factor decomposition, macro regime, and uncertainty quantification prompts.
    """
    if not tier0_outputs:
        return []

    prompt = ""
    for out in tier0_outputs:
        prompt += f"\nFor ticker {out.ticker}:\n"

        if out.solvency:
            prompt += f"[SOLVENCY & LIQUIDITY] {out.solvency.model_dump_json()}\n"
        else:
            prompt += "[SOLVENCY & LIQUIDITY] Data unavailable\n"

        if out.efficiency:
            prompt += f"[EFFICIENCY & TURNOVER] {out.efficiency.model_dump_json()}\n"
        else:
            prompt += "[EFFICIENCY & TURNOVER] Data unavailable\n"

        if out.profitability:
            prompt += f"[PROFITABILITY] {out.profitability.model_dump_json()}\n"
        else:
            prompt += "[PROFITABILITY] Data unavailable\n"

        if out.investor_behavior:
            prompt += f"[INVESTOR_BEHAVIOR] {out.investor_behavior.model_dump_json()}\n"
        else:
            prompt += "[INVESTOR_BEHAVIOR] Data unavailable\n"

        if out.technical:
            prompt += f"[TECHNICAL] {out.technical.model_dump_json()}\n"
        else:
            prompt += "[TECHNICAL] Data unavailable\n"

        if out.normalized_metrics:
            prompt += f"[NORMALIZED_VS_PEERS] {out.normalized_metrics.model_dump_json()}\n"

        # Factor decomposition context
        if out.factor_exposure:
            prompt += f"[FACTOR_DECOMPOSITION] {out.factor_exposure.model_dump_json()}\n"
            prompt += (
                "NOTE: When interpreting historical return performance, account for these "
                "known factor exposures and focus your analysis on the alpha component "
                "(the residual return after factor adjustment) rather than total return.\n"
            )

        # Macro regime context
        if out.macro_regime:
            prompt += f"[MACRO_CONTEXT] {out.macro_regime.model_dump_json()}\n"

        # Options signals
        if out.options_signals:
            prompt += f"[OPTIONS_SIGNALS] {out.options_signals.model_dump_json()}\n"

        # Institutional flow
        if out.institutional_flow:
            prompt += f"[INSTITUTIONAL_FLOW] {out.institutional_flow.model_dump_json()}\n"

        # Data quality context
        if out.data_quality:
            prompt += f"[DATA_QUALITY] Score: {out.data_quality.quality_score}, Missing: {out.data_quality.fields_missing}\n"

    system_instruction = """
    You are a quantitative analyst. For each ticker below, you have independent data sections.
    Reason about EACH section using ONLY the data in that section — do not let one section's 
    data influence another's interpretation.
    
    IMPORTANT: For each assessment you make, you MUST provide:
    1. A confidence score from 0.0 to 1.0 where 1.0 means all evidence strongly supports 
       your conclusion with no contradictions.
    2. Your rationale referencing specific data points.
    
    If any data section shows "Data unavailable", reduce your confidence for that 
    assessment and note the data gap.
    
    When factor decomposition data is provided, focus your analysis on alpha (residual 
    returns after factor adjustment) rather than total return. Explain whether returns 
    are explained by factor tilts or genuine stock-specific performance.
    
    Account for the macro regime context when interpreting fundamental signals. A 
    deteriorating current ratio is more alarming in a tightening rate environment.
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
        logger.error(f"Error parsing Quant Synthesizer JSON. Raw output: {parsed_batch}")
        return []
