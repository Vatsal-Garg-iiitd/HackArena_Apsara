import asyncio
from datetime import date
from typing import List, Dict, Any
from pipeline.infra.cache import cache
from pipeline.tier0_numeric import generate_tier0_output
from pipeline.tier1_llm.quant_synthesizer import run_quant_synthesizer
from pipeline.tier1_llm.narrative_synthesizer import run_narrative_synthesizer
from pipeline.tier2_llm.general_expert import run_general_expert

def current_quarter() -> str:
    """Mock logic for current quarter."""
    return f"{date.today().year}Q{(date.today().month-1)//3 + 1}"

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

async def run_pipeline(tickers: List[str], force_refresh: bool = False) -> Dict[str, Any]:
    results = {}
    today_str = str(date.today())
    quarter_str = current_quarter()
    
    print(f"Starting MoE Pipeline for {len(tickers)} tickers...")
    
    # Run Tier 0 for all (Using asyncio.to_thread to avoid blocking event loop with yfinance requests)
    tier0_outputs = {}
    async def fetch_tier0(ticker: str):
        print(f"Running Tier 0 for {ticker}...")
        try:
            # yfinance makes blocking HTTP calls, so we run it in a thread
            out = await asyncio.to_thread(generate_tier0_output, ticker)
            tier0_outputs[ticker] = out
        except Exception as e:
            print(f"Error in Tier 0 for {ticker}: {e}")
            tier0_outputs[ticker] = None
            
    await asyncio.gather(*(fetch_tier0(t) for t in tickers))
        
    # Tier 1A: Batch processing with max 3 tickers per chunk
    tier1a_outputs = {}
    tickers_to_run_1a = []
    
    for ticker in tickers:
        if not tier0_outputs.get(ticker):
            continue
            
        t1a_cache_key = f"{ticker}:{today_str}:quant_v1"
        tier1a_out = cache.get(t1a_cache_key) if not force_refresh else None
        
        if tier1a_out:
            print(f"Tier 1A Cache Hit for {ticker}.")
            tier1a_outputs[ticker] = tier1a_out
        else:
            tickers_to_run_1a.append(ticker)
            
    # Process Tier 1A in chunks of 3 (Sequentially across chunks to avoid massive spikes, but async within the chunk generation)
    for chunk in chunk_list(tickers_to_run_1a, 3):
        print(f"Running Tier 1A Quant Synthesizer for chunk: {chunk}...")
        tier0_chunk = [tier0_outputs[t] for t in chunk]
        # run_quant_synthesizer is now async!
        t1a_res_list = await run_quant_synthesizer(tier0_chunk)
        
        # Match results back to tickers
        for res in t1a_res_list:
            t = res.get("ticker")
            if t in chunk:
                tier1a_outputs[t] = res
                cache.set(f"{t}:{today_str}:quant_v1", res)

    # Tier 1B Narrative (Cache per quarter/filing)
    tier1b_outputs = {}
    async def run_1b_for_ticker(ticker: str):
        t1b_cache_key = f"{ticker}:{quarter_str}:narrative_v1"
        tier1b_out = cache.get(t1b_cache_key) if not force_refresh else None
            
        if tier1b_out:
            print(f"Tier 1B Cache Hit for {ticker}.")
            tier1b_outputs[ticker] = tier1b_out
        else:
            print(f"Running Tier 1B Narrative Synthesizer for {ticker}...")
            out = await run_narrative_synthesizer(ticker)
            if out:
                cache.set(t1b_cache_key, out)
            tier1b_outputs[ticker] = out
            
    await asyncio.gather(*(run_1b_for_ticker(t) for t in tickers if tier0_outputs.get(t)))

    # Tier 2 General Expert
    async def run_2_for_ticker(ticker: str):
        t2_cache_key = f"{ticker}:{today_str}:general_v1"
        tier2_out = cache.get(t2_cache_key) if not force_refresh else None
            
        if tier2_out:
            print(f"Tier 2 Cache Hit for {ticker}.")
            results[ticker] = tier2_out
        else:
            print(f"Running Tier 2 General Expert for {ticker}...")
            t1a = tier1a_outputs.get(ticker, {})
            t1b = tier1b_outputs.get(ticker, {})
            out = await run_general_expert(ticker, t1a, t1b)
            if out:
                cache.set(t2_cache_key, out)
            results[ticker] = out
            
        sig = results[ticker].get("signals", {}) if results.get(ticker) else {}
        print(f"Final Signal for {ticker}: Tactical={sig.get('tactical_horizon_30d', 'UNKNOWN')}, Structural={sig.get('structural_horizon_1y', 'UNKNOWN')}")
        
    await asyncio.gather(*(run_2_for_ticker(t) for t in tickers if tier0_outputs.get(t)))
            
    return results
