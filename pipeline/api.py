"""
FastAPI surface for the HackArena pipeline.

Run with:
    uvicorn pipeline.api:app --reload
"""

import asyncio
import os
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pipeline.infra.tavily_client import fetch_recent_news
from pipeline.orchestrator import run_pipeline
from pipeline.preprocessing.earnings_call import process_latest_earnings_call


class PipelineRunRequest(BaseModel):
    tickers: List[str] = Field(..., min_length=1, description="Ticker symbols to analyze.")
    force_refresh: bool = Field(False, description="Ignore cached LLM outputs.")
    mode: Literal["fast", "standard", "deep"] = Field(
        "fast",
        description="Latency/detail tradeoff. fast is best for interactive API calls.",
    )


class PipelineRunResponse(BaseModel):
    results: Dict[str, Any]


class NewsResponse(BaseModel):
    ticker: str
    provider: str
    api_key_configured: bool
    results: List[Dict[str, Any]]
    formatted: str
    error: Optional[str] = None


class EarningsResponse(BaseModel):
    ticker: str
    available: bool
    data: Dict[str, Any]


class TickerContextResponse(BaseModel):
    ticker: str
    news: Dict[str, Any]
    earnings_call: Dict[str, Any]


app = FastAPI(
    title="HackArena Pipeline API",
    version="0.1.0",
    description="API endpoints for pipeline orchestration, Tavily news, and earnings-call preprocessing.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("API_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _normalize_ticker(ticker: str) -> str:
    cleaned = ticker.strip().upper()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty.")
    return cleaned


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "hackarena-pipeline-api",
        "tavily_configured": bool(os.getenv("TAVILY_API_KEY")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "finnhub_configured": bool(os.getenv("FINNHUB_API_KEY")),
        "polygon_configured": bool(os.getenv("POLYGON_API_KEY")),
    }


@app.get("/v1/config")
async def config() -> Dict[str, Any]:
    return {
        "pipeline_modes": ["fast", "standard", "deep"],
        "defaults": {
            "mode": "fast",
            "tavily_max_results": 5,
        },
        "env": {
            "gemini_max_concurrent": os.getenv("GEMINI_MAX_CONCURRENT", "2"),
            "tier1a_batch_concurrency": os.getenv("TIER1A_BATCH_CONCURRENCY", "2"),
            "data_vendor": os.getenv("DATA_VENDOR", "auto"),
            "transcript_source": os.getenv("TRANSCRIPT_SOURCE", "auto"),
        },
    }


@app.post("/v1/pipeline/run", response_model=PipelineRunResponse)
async def run_pipeline_endpoint(payload: PipelineRunRequest) -> PipelineRunResponse:
    tickers = [_normalize_ticker(ticker) for ticker in payload.tickers]
    try:
        results = await run_pipeline(
            tickers,
            force_refresh=payload.force_refresh,
            mode=payload.mode,
        )
        return PipelineRunResponse(results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline run failed: {e}") from e


@app.get("/v1/news/{ticker}", response_model=NewsResponse)
async def tavily_news_endpoint(
    ticker: str,
    max_results: int = Query(5, ge=1, le=10),
) -> NewsResponse:
    symbol = _normalize_ticker(ticker)
    data = await asyncio.to_thread(fetch_recent_news, symbol, max_results)
    return NewsResponse(**data)


@app.get("/v1/earnings/{ticker}/important-parts", response_model=EarningsResponse)
async def earnings_important_parts_endpoint(
    ticker: str,
    source: Literal["auto", "mock", "finnhub", "edgar"] = Query("auto"),
) -> EarningsResponse:
    symbol = _normalize_ticker(ticker)
    try:
        data = await asyncio.to_thread(process_latest_earnings_call, symbol, source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Earnings call preprocessing failed: {e}") from e

    return EarningsResponse(
        ticker=symbol,
        available=bool(data),
        data=data or {},
    )


@app.get("/v1/tickers/{ticker}/context", response_model=TickerContextResponse)
async def ticker_context_endpoint(
    ticker: str,
    max_news_results: int = Query(5, ge=1, le=10),
    earnings_source: Literal["auto", "mock", "finnhub", "edgar"] = Query("auto"),
) -> TickerContextResponse:
    symbol = _normalize_ticker(ticker)
    news_task = asyncio.to_thread(fetch_recent_news, symbol, max_news_results)
    earnings_task = asyncio.to_thread(process_latest_earnings_call, symbol, earnings_source)
    news, earnings = await asyncio.gather(news_task, earnings_task)

    return TickerContextResponse(
        ticker=symbol,
        news=news,
        earnings_call={
            "available": bool(earnings),
            "data": earnings or {},
        },
    )
