"""
Semantic Consistency Checker.
Validates that LLM qualitative assessments are numerically consistent
with the data that was passed to them. Catches error compounding between tiers.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConsistencyRule:
    """A single consistency constraint."""
    def __init__(self, name: str, llm_field: str, llm_values: list,
                 data_field: str, data_check: callable, message: str):
        self.name = name
        self.llm_field = llm_field        # dot-notation path in LLM output
        self.llm_values = llm_values      # LLM values that trigger this check
        self.data_field = data_field      # dot-notation path in data
        self.data_check = data_check      # callable(data_value) -> bool
        self.message = message


# Rule library for Tier 1A consistency
TIER1A_RULES = [
    ConsistencyRule(
        name="solvency_adequate_requires_cr_above_1",
        llm_field="solvency_read.trend",
        llm_values=["improving", "stable"],
        data_field="solvency.current_ratio",
        data_check=lambda x: x is not None and x >= 0.8,  # slight tolerance
        message="LLM says solvency is {llm_val} but current ratio is {data_val} (expected >= 0.8)"
    ),
    ConsistencyRule(
        name="debt_manageable_requires_de_below_3",
        llm_field="solvency_read.trend",
        llm_values=["improving", "stable"],
        data_field="solvency.debt_equity",
        data_check=lambda x: x is None or x <= 3.0,  # None = no debt data
        message="LLM says solvency is {llm_val} but debt/equity is {data_val} (expected <= 3.0)"
    ),
    ConsistencyRule(
        name="profitability_strong_requires_positive_margins",
        llm_field="profitability_read.strength",
        llm_values=["strong"],
        data_field="profitability.operating_margin",
        data_check=lambda x: x is not None and x > 0,
        message="LLM says profitability is {llm_val} but operating margin is {data_val} (expected > 0)"
    ),
    ConsistencyRule(
        name="technical_overbought_requires_high_rsi",
        llm_field="technical_read.signal",
        llm_values=["overbought"],
        data_field="technical.rsi_14",
        data_check=lambda x: x is not None and x > 55,
        message="LLM says overbought but RSI is {data_val} (expected > 55)"
    ),
    ConsistencyRule(
        name="technical_oversold_requires_low_rsi",
        llm_field="technical_read.signal",
        llm_values=["oversold"],
        data_field="technical.rsi_14",
        data_check=lambda x: x is not None and x < 45,
        message="LLM says oversold but RSI is {data_val} (expected < 45)"
    ),
]


def _get_nested_value(data: Dict[str, Any], dotpath: str) -> Any:
    """Get a value from a nested dict using dot notation."""
    keys = dotpath.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif hasattr(current, key):
            current = getattr(current, key)
        else:
            return None
        if current is None:
            return None
    return current


class SemanticConsistencyChecker:
    """
    Validates LLM outputs against the underlying data.
    Detects when LLM claims contradict the numbers that were provided.
    """

    CONFIDENCE_PENALTY = 0.30  # 30% penalty per inconsistency

    def check_tier1a(
        self,
        llm_output: Dict[str, Any],
        tier0_data: Dict[str, Any],
    ) -> Tuple[List[Dict[str, str]], float]:
        """
        Check Tier 1A LLM output against Tier 0 data.

        Returns:
            - List of inconsistency dicts with 'rule', 'message' keys
            - Adjusted confidence multiplier (1.0 = no issues, lower = issues found)
        """
        inconsistencies = []
        confidence_multiplier = 1.0

        for rule in TIER1A_RULES:
            llm_val = _get_nested_value(llm_output, rule.llm_field)

            if llm_val is None or llm_val not in rule.llm_values:
                continue  # Rule doesn't apply to this output

            data_val = _get_nested_value(tier0_data, rule.data_field)

            if not rule.data_check(data_val):
                msg = rule.message.format(llm_val=llm_val, data_val=data_val)
                inconsistencies.append({
                    "rule": rule.name,
                    "message": msg,
                })
                logger.warning(f"SEMANTIC_INCONSISTENCY_DETECTED | rule={rule.name} | {msg}")
                confidence_multiplier *= (1.0 - self.CONFIDENCE_PENALTY)

        return inconsistencies, round(confidence_multiplier, 4)

    def check_tier2(
        self,
        llm_output: Dict[str, Any],
        tier1a_data: Dict[str, Any],
        tier1b_data: Dict[str, Any],
    ) -> Tuple[List[Dict[str, str]], float]:
        """
        Check Tier 2 output for internal consistency with Tier 1 inputs.
        E.g., if Tier 1A says deteriorating solvency and Tier 1B says negative outlook,
        Tier 2 should not output "buy" with "high" confidence.
        """
        inconsistencies = []
        confidence_multiplier = 1.0

        # Check: if both quant and narrative are negative, signal shouldn't be bullish
        solvency_trend = _get_nested_value(tier1a_data, "solvency_read.trend")
        profit_strength = _get_nested_value(tier1a_data, "profitability_read.strength")
        news_tone = _get_nested_value(tier1b_data, "news_sentiment.tone")
        earnings_tone = _get_nested_value(tier1b_data, "earnings_read.tone")

        negative_count = 0
        if solvency_trend == "deteriorating":
            negative_count += 1
        if profit_strength == "weak":
            negative_count += 1
        if news_tone == "negative":
            negative_count += 1
        if earnings_tone == "negative":
            negative_count += 1

        signals = llm_output.get("signals", {})
        tactical = signals.get("tactical_horizon_30d")
        structural = signals.get("structural_horizon_1y")
        confidence = llm_output.get("confidence")

        # If 3+ signals are negative but output is buy with high confidence
        if negative_count >= 3:
            if tactical == "buy" and confidence == "high":
                msg = f"3+ negative signals from Tier1 but Tier2 says tactical buy with high confidence"
                inconsistencies.append({"rule": "negative_signals_vs_buy", "message": msg})
                logger.warning(f"SEMANTIC_INCONSISTENCY_DETECTED | {msg}")
                confidence_multiplier *= (1.0 - self.CONFIDENCE_PENALTY)

            if structural == "buy" and confidence == "high":
                msg = f"3+ negative signals from Tier1 but Tier2 says structural buy with high confidence"
                inconsistencies.append({"rule": "negative_signals_vs_structural_buy", "message": msg})
                logger.warning(f"SEMANTIC_INCONSISTENCY_DETECTED | {msg}")
                confidence_multiplier *= (1.0 - self.CONFIDENCE_PENALTY)

        return inconsistencies, round(confidence_multiplier, 4)

    def build_correction_prompt(self, inconsistencies: List[Dict[str, str]]) -> str:
        """
        Build a correction prompt for the LLM retry, explicitly listing
        the contradictions found.
        """
        corrections = "\n".join([
            f"- {inc['message']}" for inc in inconsistencies
        ])
        return (
            f"Your previous assessment contained the following inconsistencies "
            f"with the actual data:\n{corrections}\n\n"
            f"Please revise your assessment to be consistent with the actual data values. "
            f"If the data truly supports a different conclusion than what the numbers suggest, "
            f"explain why explicitly."
        )


# Global instance
consistency_checker = SemanticConsistencyChecker()
