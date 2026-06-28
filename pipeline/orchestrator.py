"""
Pipeline Orchestrator.
Wires all tiers together with:
- Proper None-propagation (skips tickers with missing critical data)
- Semantic consistency checking between tiers
- Structured logging and run summary reports
- Data quality tracking
"""

import asyncio
import logging
from datetime import date
from typing import List, Dict, Any

from pipeline.infra.cache import cache
from pipeline.infra.consistency_checker import consistency_checker
from pipeline.infra.logging_config import PipelineRunTracker
from pipeline.tier0_numeric import generate_tier0_output
from pipeline.tier1_llm.quant_synthesizer import run_quant_synthesizer
from pipeline.tier1_llm.narrative_synthesizer import run_narrative_synthesizer
from pipeline.tier1_llm.ohlcv_analyzer import run_ohlcv_analyzer
from pipeline.tier2_llm.general_expert import run_general_expert

logger = logging.getLogger(__name__)


def current_quarter() -> str:
    return f"{date.today().year}Q{(date.today().month - 1) // 3 + 1}"


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


async def run_pipeline(tickers: List[str], force_refresh: bool = False) -> Dict[str, Any]:
    results = {}
    today_str = str(date.today())
    quarter_str = current_quarter()

    # Initialize run tracker
    tracker = PipelineRunTracker()
    tracker.summary.tickers_requested = len(tickers)

    print(f"\n{'='*60}")
    print(f"  Pipeline Run {tracker.run_id} — {len(tickers)} tickers")
    print(f"{'='*60}\n")

    # =====================================================================
    # TIER 0: Numeric Engine (pure code, no LLM)
    # =====================================================================
    tier0_outputs = {}

    async def fetch_tier0(ticker: str):
        with tracker.track_stage("tier0", ticker) as metrics:
            try:
                out = await asyncio.to_thread(generate_tier0_output, ticker)
                if out is None:
                    tracker.record_data_quality_failure(ticker, "tier0", "critical_data_missing")
                    tracker.summary.tickers_skipped += 1
                    print(f"  ✗ {ticker}: Tier 0 SKIPPED (critical data missing)")
                else:
                    tier0_outputs[ticker] = out
                    quality = out.data_quality.quality_score if out.data_quality else 1.0
                    print(f"  ✓ {ticker}: Tier 0 complete (data quality: {quality:.0%})")
            except Exception as e:
                tracker.record_data_quality_failure(ticker, "tier0", str(e))
                tracker.summary.tickers_failed += 1
                print(f"  ✗ {ticker}: Tier 0 FAILED ({e})")

    await asyncio.gather(*(fetch_tier0(t) for t in tickers))

    valid_tickers = [t for t in tickers if t in tier0_outputs]
    if not valid_tickers:
        print("\n  ⚠ No tickers passed Tier 0 data quality checks. Aborting run.")
        summary = tracker.finalize()
        return {"_run_summary": summary.to_dict()}

    # =====================================================================
    # TIER 1A: Quant Synthesizer (batched LLM calls)
    # =====================================================================
    tier1a_outputs = {}
    tickers_to_run_1a = []

    for ticker in valid_tickers:
        t1a_cache_key = f"{ticker}:{today_str}:quant_v2"
        tier1a_out = cache.get(t1a_cache_key) if not force_refresh else None

        if tier1a_out:
            tracker.record_cache_hit("tier1a", ticker)
            tier1a_outputs[ticker] = tier1a_out
            print(f"  ⟳ {ticker}: Tier 1A cache hit")
        else:
            tickers_to_run_1a.append(ticker)

    for chunk in chunk_list(tickers_to_run_1a, 3):
        with tracker.track_stage("tier1a", ",".join(chunk)):
            print(f"  → Running Tier 1A for: {chunk}")
            tier0_chunk = [tier0_outputs[t] for t in chunk]
            t1a_res_list = await run_quant_synthesizer(tier0_chunk)

            for res in t1a_res_list:
                t = res.get("ticker")
                if t in chunk:
                    # Consistency check: validate LLM output against Tier 0 data
                    tier0_data = tier0_outputs[t].model_dump()
                    inconsistencies, confidence_mult = consistency_checker.check_tier1a(res, tier0_data)

                    if inconsistencies:
                        print(f"  ⚠ {t}: {len(inconsistencies)} consistency issue(s) detected (confidence: {confidence_mult:.0%})")
                        for inc in inconsistencies:
                            tracker.record_inconsistency()
                            logger.warning(f"INCONSISTENCY | {t} | {inc['rule']}: {inc['message']}")

                    tier1a_outputs[t] = res
                    cache.set(f"{t}:{today_str}:quant_v2", res)

    # =====================================================================
    # TIER 1B: Narrative Synthesizer (one ticker at a time, cached per quarter)
    # =====================================================================
    tier1b_outputs = {}

    async def run_1b_for_ticker(ticker: str):
        t1b_cache_key = f"{ticker}:{quarter_str}:narrative_v2"
        tier1b_out = cache.get(t1b_cache_key) if not force_refresh else None

        if tier1b_out:
            tracker.record_cache_hit("tier1b", ticker)
            tier1b_outputs[ticker] = tier1b_out
            print(f"  ⟳ {ticker}: Tier 1B cache hit")
        else:
            with tracker.track_stage("tier1b", ticker):
                print(f"  → Running Tier 1B for: {ticker}")
                out = await run_narrative_synthesizer(ticker)
                if out:
                    cache.set(t1b_cache_key, out)
                tier1b_outputs[ticker] = out

    await asyncio.gather(*(run_1b_for_ticker(t) for t in valid_tickers))

    # =====================================================================
    # TIER 1C: Raw OHLCV Analyzer (deterministic yfinance market structure)
    # =====================================================================
    tier1c_outputs = {}
    tickers_to_run_1c = []

    for ticker in valid_tickers:
        t1c_cache_key = f"{ticker}:{today_str}:ohlcv_v1"
        tier1c_out = cache.get(t1c_cache_key) if not force_refresh else None

        if tier1c_out:
            tracker.record_cache_hit("tier1c", ticker)
            tier1c_outputs[ticker] = tier1c_out
            print(f"  ⟳ {ticker}: Tier 1C cache hit")
        else:
            tickers_to_run_1c.append(ticker)

    if tickers_to_run_1c:
        with tracker.track_stage("tier1c", ",".join(tickers_to_run_1c)):
            print(f"  → Running Tier 1C raw OHLCV analyzer for: {tickers_to_run_1c}")
            t1c_map = await run_ohlcv_analyzer(tickers_to_run_1c)

            for ticker, analysis in t1c_map.items():
                payload = analysis.model_dump(mode="json")
                tier1c_outputs[ticker] = payload
                cache.set(f"{ticker}:{today_str}:ohlcv_v1", payload)

    # =====================================================================
    # TIER 2: General Expert (synthesis + final signal)
    # =====================================================================
    async def run_2_for_ticker(ticker: str):
        t2_cache_key = f"{ticker}:{today_str}:general_v3"
        tier2_out = cache.get(t2_cache_key) if not force_refresh else None

        if tier2_out:
            tracker.record_cache_hit("tier2", ticker)
            results[ticker] = tier2_out
            print(f"  ⟳ {ticker}: Tier 2 cache hit")
        else:
            with tracker.track_stage("tier2", ticker):
                print(f"  → Running Tier 2 for: {ticker}")
                t1a = tier1a_outputs.get(ticker, {})
                t1b = tier1b_outputs.get(ticker, {})
                t1c = tier1c_outputs.get(ticker, {})

                # Gather consistency flags from Tier 1A
                tier0_data = tier0_outputs[ticker].model_dump()
                inconsistencies_1a, _ = consistency_checker.check_tier1a(t1a, tier0_data)
                consistency_flags = [inc["message"] for inc in inconsistencies_1a]

                # Get macro regime context
                macro = tier0_outputs[ticker].macro_regime
                macro_context = macro.context_string if macro else None

                out = await run_general_expert(
                    ticker, t1a, t1b, t1c,
                    macro_regime=macro_context,
                    consistency_flags=consistency_flags if consistency_flags else None,
                )

                if out:
                    # Consistency check Tier 2
                    t2_inconsistencies, t2_conf = consistency_checker.check_tier2(out, t1a, t1b)
                    if t2_inconsistencies:
                        print(f"  ⚠ {ticker}: {len(t2_inconsistencies)} Tier 2 consistency issue(s)")
                        for inc in t2_inconsistencies:
                            tracker.record_inconsistency()
                        out["consistency_flags"] = out.get("consistency_flags", []) + [
                            inc["message"] for inc in t2_inconsistencies
                        ]

                    cache.set(t2_cache_key, out)
                results[ticker] = out

        # Print final signal
        if results.get(ticker):
            sig = results[ticker].get("signals", {})
            conf = results[ticker].get("overall_confidence", "?")
            tactical = sig.get("tactical_horizon_30d", {})
            structural = sig.get("structural_horizon_1y", {})

            if isinstance(tactical, dict):
                tac_str = f"{tactical.get('direction', '?')} ({tactical.get('confidence', '?'):.0%})" if isinstance(tactical.get('confidence'), (int, float)) else f"{tactical.get('direction', '?')}"
            else:
                tac_str = str(tactical)

            if isinstance(structural, dict):
                str_str = f"{structural.get('direction', '?')} ({structural.get('confidence', '?'):.0%})" if isinstance(structural.get('confidence'), (int, float)) else f"{structural.get('direction', '?')}"
            else:
                str_str = str(structural)

            print(f"\n  📊 {ticker}: Tactical={tac_str}, Structural={str_str}, Overall Confidence={conf}")
        else:
            tracker.summary.tickers_failed += 1

    await asyncio.gather(*(run_2_for_ticker(t) for t in valid_tickers))

    # =====================================================================
    # RUN SUMMARY
    # =====================================================================
    tracker.summary.tickers_succeeded = len([t for t in valid_tickers if t in results and results[t]])

    summary = tracker.finalize()

    print(f"\n{'='*60}")
    print(f"  Run Summary ({tracker.run_id})")
    print(f"{'='*60}")
    print(f"  Tickers: {summary.tickers_requested} requested, {summary.tickers_succeeded} succeeded, "
          f"{summary.tickers_failed} failed, {summary.tickers_skipped} skipped")
    print(f"  Duration: {summary.total_duration_ms:.0f}ms")
    print(f"  Cache hit rate: {summary.cache_hit_rate:.0%}")
    print(f"  Semantic inconsistencies: {summary.semantic_inconsistencies}")
    if summary.data_quality_failures:
        print(f"  Data quality failures: {len(summary.data_quality_failures)}")
        for dqf in summary.data_quality_failures[:5]:
            print(f"    - {dqf}")
    print(f"{'='*60}\n")

    # Save run history to cache
    try:
        cache.save_run_history(tracker.run_id, summary.to_dict())
    except Exception:
        pass

    results["_run_summary"] = summary.to_dict()
    return results
