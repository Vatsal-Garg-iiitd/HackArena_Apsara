"""
FastAPI surface for the HackArena MoE pipeline.

Run with:
    uvicorn pipeline.api:app --reload
"""

import asyncio
import os
from datetime import date
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pipeline.infra.tavily_client import fetch_recent_news
from pipeline.orchestrator import run_pipeline
from pipeline.preprocessing.earnings_call import process_latest_earnings_call
from pipeline.tier0_numeric import generate_tier0_output


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


class ScoreWithRationale(BaseModel):
    score: Literal["strong", "moderate", "weak"]
    rationale: str


class ValuationScoreWithRationale(BaseModel):
    score: Literal["attractive", "fair", "expensive"]
    rationale: str


class DimensionScores(BaseModel):
    revenue_quality: ScoreWithRationale
    balance_sheet_health: ScoreWithRationale
    cash_flow_quality: ScoreWithRationale
    competitive_position: ScoreWithRationale
    valuation_attractiveness: ValuationScoreWithRationale


class PeerComparison(BaseModel):
    gross_margin_vs_peers: str
    current_ratio_vs_peers: str
    overall_peer_standing: Literal["leader", "in-line", "laggard"]


class SmartMoneyRead(BaseModel):
    insider_signal: Literal["bullish", "neutral", "bearish"]
    institutional_signal: Literal["accumulating", "stable", "distributing"]
    rationale: str


class RiskAssessment(BaseModel):
    identified_risks: List[str]
    severity: Literal["high", "medium", "low"]
    mitigating_factors: List[str]


class ForwardOutlook(BaseModel):
    eps_revision_commentary: str
    guidance_commentary: str
    analyst_consensus_commentary: str


class MacroFit(BaseModel):
    regime: str
    impact_on_this_stock: str


class SignalWithConfidence(BaseModel):
    signal: Literal["buy", "hold", "sell"]
    confidence: Literal["high", "medium", "low"]
    rationale: str


class FinalSignals(BaseModel):
    tactical_30d: SignalWithConfidence
    structural_1y: SignalWithConfidence


class FundamentalAnalysisOutput(BaseModel):
    ticker: str
    analysis_date: str
    executive_summary: str
    dimension_scores: DimensionScores
    peer_comparison: PeerComparison
    smart_money_read: SmartMoneyRead
    risk_assessment: RiskAssessment
    forward_outlook: ForwardOutlook
    macro_fit: MacroFit
    conflicting_signals: List[str]
    final_signals: FinalSignals
    one_line_verdict: str
    source_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw MoE/Tier 0 data used to build the report.",
    )


app = FastAPI(
    title="HackArena Pipeline API",
    version="0.2.0",
    description="API endpoints for orchestration, Tavily news, earnings calls, and MoE-backed fundamental analysis.",
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


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "not available"
    return f"{value * 100:.1f}%"


def _fmt_num(value: Optional[float]) -> str:
    if value is None:
        return "not available"
    return f"{value:.2f}"


def _trend_label(values: List[float]) -> str:
    if len(values) < 2:
        return "trend unavailable"
    if values[-1] > values[0]:
        return "improving"
    if values[-1] < values[0]:
        return "deteriorating"
    return "stable"


def _diff_comment(metric: Optional[float], label: str, unit: str = "points") -> str:
    if metric is None:
        return f"{label} peer comparison is unavailable in the current MoE output."
    direction = "above" if metric > 0 else "below" if metric < 0 else "in line with"
    amount = abs(metric)
    return f"{label} is {direction} peers by {amount:.2f} {unit}."


def _build_risk_flags(tier0: Dict[str, Any]) -> List[str]:
    risks = []
    solvency = tier0.get("solvency") or {}
    normalized = tier0.get("normalized_metrics") or {}
    data_quality = tier0.get("data_quality") or {}

    current_ratio = solvency.get("current_ratio")
    debt_equity = solvency.get("debt_equity")
    gross_margin_vs_peers = normalized.get("gross_margin_vs_peers")
    current_ratio_vs_peers = normalized.get("current_ratio_vs_peers")

    if current_ratio is None:
        risks.append("current_ratio_unavailable")
    elif current_ratio < 1.0:
        risks.append("current_ratio_below_1")
    if current_ratio_vs_peers is not None and current_ratio_vs_peers < 0:
        risks.append("current_ratio_below_peers")
    if debt_equity is not None and debt_equity > 2.0:
        risks.append("high_debt_equity_ratio")
    if gross_margin_vs_peers is not None and gross_margin_vs_peers < 0:
        risks.append("gross_margin_below_peers")
    if data_quality.get("quality_score", 1.0) < 0.7:
        risks.append("low_data_quality")
    risks.append("valuation_data_unavailable")
    return risks


def _score_balance_sheet(tier0: Dict[str, Any]) -> ScoreWithRationale:
    solvency = tier0.get("solvency") or {}
    current_ratio = solvency.get("current_ratio")
    debt_equity = solvency.get("debt_equity")
    interest_coverage = solvency.get("interest_coverage")
    trend = _trend_label(solvency.get("trend_8q") or [])

    positives = 0
    if current_ratio is not None and current_ratio >= 1.0:
        positives += 1
    if debt_equity is not None and debt_equity <= 2.0:
        positives += 1
    if interest_coverage is not None and interest_coverage >= 5.0:
        positives += 1

    score = "strong" if positives >= 3 else "moderate" if positives >= 1 else "weak"
    rationale = (
        f"Current ratio is {_fmt_num(current_ratio)}, debt/equity is {_fmt_num(debt_equity)}, "
        f"and interest coverage is {_fmt_num(interest_coverage)}. The 8-quarter liquidity trend is {trend}."
    )
    return ScoreWithRationale(score=score, rationale=rationale)


def _score_cash_flow(tier0: Dict[str, Any]) -> ScoreWithRationale:
    solvency = tier0.get("solvency") or {}
    op_cash_flow_ratio = solvency.get("op_cash_flow_ratio")
    cash_flow_debt = solvency.get("cash_flow_debt")

    if op_cash_flow_ratio is not None and op_cash_flow_ratio > 0.5:
        score = "strong"
    elif op_cash_flow_ratio is not None and op_cash_flow_ratio > 0:
        score = "moderate"
    else:
        score = "weak"

    rationale = (
        f"MoE provides operating cash flow ratio of {_fmt_num(op_cash_flow_ratio)} "
        f"and cash-flow-to-debt of {_fmt_num(cash_flow_debt)}. Free cash flow and capex metrics "
        "are not yet exposed in Tier 0, so this score is based on available cash conversion proxies."
    )
    return ScoreWithRationale(score=score, rationale=rationale)


def _score_profitability(tier0: Dict[str, Any]) -> ScoreWithRationale:
    profitability = tier0.get("profitability") or {}
    normalized = tier0.get("normalized_metrics") or {}
    gross_margin = profitability.get("gross_margin")
    operating_margin = profitability.get("operating_margin")
    roe = profitability.get("roe")
    gross_margin_vs_peers = normalized.get("gross_margin_vs_peers")
    roe_vs_peers = normalized.get("roe_vs_peers")

    positives = 0
    if gross_margin is not None and gross_margin > 0.3:
        positives += 1
    if operating_margin is not None and operating_margin > 0.15:
        positives += 1
    if roe_vs_peers is not None and roe_vs_peers > 0:
        positives += 1

    score = "strong" if positives >= 2 else "moderate" if positives == 1 else "weak"
    rationale = (
        f"Gross margin is {_fmt_pct(gross_margin)}, operating margin is {_fmt_pct(operating_margin)}, "
        f"and ROE is {_fmt_pct(roe)}. Gross margin peer delta is {_fmt_num(gross_margin_vs_peers)} "
        f"and ROE peer delta is {_fmt_num(roe_vs_peers)}."
    )
    return ScoreWithRationale(score=score, rationale=rationale)


def _score_competitive_position(tier0: Dict[str, Any]) -> ScoreWithRationale:
    peer = tier0.get("peer_dynamics") or {}
    normalized = tier0.get("normalized_metrics") or {}
    peer_confidence = peer.get("peer_confidence")
    sharpe_rank = peer.get("percentile_rank_sharpe")
    gross_margin_vs_peers = normalized.get("gross_margin_vs_peers")

    if gross_margin_vs_peers is not None and gross_margin_vs_peers > 0 and (sharpe_rank or 0) >= 50:
        score = "strong"
    elif gross_margin_vs_peers is not None or sharpe_rank is not None:
        score = "moderate"
    else:
        score = "weak"

    rationale = (
        f"Peer confidence is {_fmt_num(peer_confidence)} and Sharpe percentile rank is {_fmt_num(sharpe_rank)}. "
        f"Gross margin peer delta is {_fmt_num(gross_margin_vs_peers)}. This is a proxy-based moat read; "
        "market share, R&D, and product-pipeline data are not yet available in Tier 0."
    )
    return ScoreWithRationale(score=score, rationale=rationale)


def _smart_money_read(tier0: Dict[str, Any]) -> SmartMoneyRead:
    investor = tier0.get("investor_behavior") or {}
    buys = investor.get("insider_buys_90d", 0)
    sells = investor.get("insider_sells_90d", 0)
    short_interest = investor.get("short_interest_delta_pct")

    insider_signal = "bullish" if buys > sells else "bearish" if sells > buys else "neutral"
    institutional_signal = "stable"

    rationale = (
        f"Insider activity shows {buys} buys and {sells} sells over 90 days. "
        f"Short interest is {_fmt_num(short_interest)}. "
        "Institutional flow data is not available for Indian market tickers."
    )
    return SmartMoneyRead(
        insider_signal=insider_signal,
        institutional_signal=institutional_signal,
        rationale=rationale,
    )


def _fundamental_report_from_tier0(tier0: Dict[str, Any]) -> FundamentalAnalysisOutput:
    ticker = tier0["ticker"]
    profitability = tier0.get("profitability") or {}
    solvency = tier0.get("solvency") or {}
    normalized = tier0.get("normalized_metrics") or {}
    macro = tier0.get("macro_regime") or {}
    technical = tier0.get("technical") or {}
    data_quality = tier0.get("data_quality") or {}
    risk_flags = _build_risk_flags(tier0)

    profitability_score = _score_profitability(tier0)
    balance_sheet_score = _score_balance_sheet(tier0)
    cash_flow_score = _score_cash_flow(tier0)
    competitive_score = _score_competitive_position(tier0)

    valuation_score = ValuationScoreWithRationale(
        score="fair",
        rationale=(
            "Valuation multiples, DCF value, and current price are not currently exposed by Tier 0. "
            "The endpoint therefore refuses to label the stock attractive or expensive without valuation data."
        ),
    )

    current_ratio_trend = _trend_label(solvency.get("trend_8q") or [])
    peer_comparison = PeerComparison(
        gross_margin_vs_peers=_diff_comment(normalized.get("gross_margin_vs_peers"), "Gross margin"),
        current_ratio_vs_peers=_diff_comment(normalized.get("current_ratio_vs_peers"), "Current ratio"),
        overall_peer_standing=(
            "leader"
            if (normalized.get("gross_margin_vs_peers") or 0) > 0 and (normalized.get("roe_vs_peers") or 0) > 0
            else "laggard"
            if (normalized.get("gross_margin_vs_peers") or 0) < 0 and (normalized.get("current_ratio_vs_peers") or 0) < 0
            else "in-line"
        ),
    )

    severity = "high" if "high_debt_equity_ratio" in risk_flags or "low_data_quality" in risk_flags else "medium"
    if len(risk_flags) <= 1:
        severity = "low"

    macro_regime = macro.get("composite_label") or normalized.get("macro_regime") or "unknown"
    macro_fit = MacroFit(
        regime=macro_regime,
        impact_on_this_stock=(
            f"Current macro read is {macro_regime}. Fed funds is {_fmt_num(macro.get('fed_funds_rate'))}%, "
            f"VIX is {_fmt_num(macro.get('vix'))}, and yield-curve spread is "
            f"{_fmt_num(macro.get('yield_curve_spread'))}%. Higher-rate or risk-off regimes place "
            "more weight on liquidity, interest coverage, and durable margins."
        ),
    )

    conflicts = []
    if profitability_score.score == "strong" and balance_sheet_score.score != "strong":
        conflicts.append(
            "Profitability is stronger than balance-sheet quality; strong margins do not fully eliminate liquidity or leverage risk."
        )
    if valuation_score.score == "fair":
        conflicts.append(
            "Fundamental quality can be assessed, but valuation attractiveness cannot be confirmed because price and multiple data are unavailable."
        )
    if technical.get("macd_signal") == "bearish" and profitability_score.score == "strong":
        conflicts.append(
            "Short-term technical momentum is bearish while profitability fundamentals are strong; this supports separating 30-day and 1-year signals."
        )

    strong_count = sum(
        score == "strong"
        for score in [
            profitability_score.score,
            balance_sheet_score.score,
            cash_flow_score.score,
            competitive_score.score,
        ]
    )
    confidence = "high" if strong_count >= 3 and severity != "high" else "medium" if strong_count >= 2 else "low"

    tactical_signal = "hold"
    if technical.get("macd_signal") == "bullish" and (technical.get("rsi_14") or 50) < 70:
        tactical_signal = "buy"
    elif technical.get("macd_signal") == "bearish" and (technical.get("rsi_14") or 50) > 45:
        tactical_signal = "sell"

    structural_signal = "buy" if strong_count >= 3 else "hold" if strong_count >= 2 else "sell"

    executive_summary = (
        f"{ticker} shows {profitability_score.score} profitability, {balance_sheet_score.score} balance-sheet health, "
        f"and {cash_flow_score.score} cash-flow quality based on MoE Tier 0 data. The most important point is that "
        f"current liquidity is {_fmt_num(solvency.get('current_ratio'))} with an {current_ratio_trend} 8-quarter trend, "
        f"while gross margin is {_fmt_pct(profitability.get('gross_margin'))}. Valuation data is not yet available, "
        "so the report separates fundamental quality from price attractiveness."
    )

    one_line = (
        f"{ticker} is a {structural_signal.upper()} on 1-year fundamentals with {confidence} confidence, "
        f"but valuation remains unresolved until price and multiple data are added."
    )

    return FundamentalAnalysisOutput(
        ticker=ticker,
        analysis_date=str(date.today()),
        executive_summary=executive_summary,
        dimension_scores=DimensionScores(
            revenue_quality=profitability_score,
            balance_sheet_health=balance_sheet_score,
            cash_flow_quality=cash_flow_score,
            competitive_position=competitive_score,
            valuation_attractiveness=valuation_score,
        ),
        peer_comparison=peer_comparison,
        smart_money_read=_smart_money_read(tier0),
        risk_assessment=RiskAssessment(
            identified_risks=risk_flags,
            severity=severity,
            mitigating_factors=[
                f"Interest coverage is {_fmt_num(solvency.get('interest_coverage'))}.",
                f"Operating margin is {_fmt_pct(profitability.get('operating_margin'))}.",
                f"Data quality score is {_fmt_num(data_quality.get('quality_score'))}.",
            ],
        ),
        forward_outlook=ForwardOutlook(
            eps_revision_commentary="EPS revision data is not currently exposed by Tier 0.",
            guidance_commentary="Guidance commentary should be pulled from the earnings-call endpoint when transcript data is available.",
            analyst_consensus_commentary="Analyst consensus and price-target data are not currently exposed by Tier 0.",
        ),
        macro_fit=macro_fit,
        conflicting_signals=conflicts or ["No major internal conflict detected in the currently available MoE fields."],
        final_signals=FinalSignals(
            tactical_30d=SignalWithConfidence(
                signal=tactical_signal,
                confidence="medium" if technical else "low",
                rationale=(
                    f"Technical MACD signal is {technical.get('macd_signal', 'unavailable')} and RSI is "
                    f"{_fmt_num(technical.get('rsi_14'))}; this drives the short-term call."
                ),
            ),
            structural_1y=SignalWithConfidence(
                signal=structural_signal,
                confidence=confidence,
                rationale=(
                    f"The 1-year call is based on {strong_count} strong dimensions across profitability, "
                    "balance sheet, cash flow, and competitive proxies."
                ),
            ),
        ),
        one_line_verdict=one_line,
        source_data=tier0,
    )


async def _generate_tier0_for_api(ticker: str, mode: str) -> Dict[str, Any]:
    # Current Tier 0 exposes a ticker-only interface. Keep mode in the public
    # API so the route can evolve with the optimized Tier 0 path without
    # breaking clients.
    tier0 = await asyncio.to_thread(generate_tier0_output, ticker)
    if tier0 is None:
        raise HTTPException(status_code=422, detail=f"Tier 0 could not produce usable data for {ticker}.")
    data = tier0.model_dump(mode="json")
    data["mode"] = mode
    return data


@app.get("/", include_in_schema=False)
async def root() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "hackarena-pipeline-api",
        "message": "Pipeline API is running.",
        "health": "/health",
        "config": "/v1/config",
        "fundamentals": "/v1/fundamentals/{ticker}",
        "pipeline": "/v1/pipeline/run",
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "hackarena-pipeline-api",
        "tavily_configured": bool(os.getenv("TAVILY_API_KEY")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "finnhub_configured": bool(os.getenv("FINNHUB_API_KEY")),
        "data_vendor": "yfinance",
    }


@app.get("/v1/config")
async def config() -> Dict[str, Any]:
    return {
        "pipeline_modes": ["fast", "standard", "deep"],
        "defaults": {
            "mode": "fast",
            "fundamental_mode": "standard",
            "tavily_max_results": 5,
        },
        "env": {
            "gemini_max_concurrent": os.getenv("GEMINI_MAX_CONCURRENT", "2"),
            "tier1a_batch_concurrency": os.getenv("TIER1A_BATCH_CONCURRENCY", "2"),
            "data_vendor": "yfinance",
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
        )
        return PipelineRunResponse(results=results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline run failed: {e}") from e


@app.get("/v1/fundamentals/{ticker}", response_model=FundamentalAnalysisOutput)
async def fundamental_analysis_from_moe_endpoint(
    ticker: str,
    mode: Literal["standard", "deep"] = Query(
        "standard",
        description="Use standard for faster peer-aware fundamentals, deep for extended options/factor/institutional fields.",
    ),
) -> FundamentalAnalysisOutput:
    symbol = _normalize_ticker(ticker)
    tier0 = await _generate_tier0_for_api(symbol, mode)
    return _fundamental_report_from_tier0(tier0)


@app.get("/v1/fundamentals/{ticker}/data")
async def fundamental_source_data_endpoint(
    ticker: str,
    mode: Literal["fast", "standard", "deep"] = Query("standard"),
) -> Dict[str, Any]:
    symbol = _normalize_ticker(ticker)
    return {
        "ticker": symbol,
        "mode": mode,
        "tier0": await _generate_tier0_for_api(symbol, mode),
    }


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
    source: Literal["auto", "mock", "finnhub"] = Query("auto"),
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
    earnings_source: Literal["auto", "mock", "finnhub"] = Query("auto"),
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
