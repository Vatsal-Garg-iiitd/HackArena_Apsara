import argparse
import json
import asyncio
from pipeline.orchestrator import run_pipeline

async def main():
    parser = argparse.ArgumentParser(description="MoE Pipeline (Prototype)")
    parser.add_argument("--tickers", type=str, required=True, help="Comma separated tickers (e.g. AAPL,MSFT)")
    parser.add_argument("--refresh-all", action="store_true", help="Force ignoring all caches")
    parser.add_argument(
        "--mode",
        choices=["fast", "standard", "deep"],
        default="deep",
        help="Latency/detail tradeoff. fast skips peer and extended Tier 0 metrics; deep runs everything.",
    )
    
    args = parser.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    
    results = await run_pipeline(tickers, force_refresh=args.refresh_all, mode=args.mode)
    
    print("\n================ FINAL RESULTS ================\n")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
