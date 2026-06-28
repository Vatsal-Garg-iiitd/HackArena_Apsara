"use client";

import Link from "next/link";
import { ArrowDown, ArrowLeft, ArrowUp, Activity, Trash2, CheckCircle2, XCircle, AlertTriangle, RefreshCw, Info, Scale, ShieldAlert, Sparkles, HeartPulse } from "lucide-react";
import { MouseEvent, useEffect, useMemo, useState } from "react";
import { ProfileMenu } from "@/components/auth/ProfileMenu";
import { getPortfolioItems, PortfolioItem, removePortfolioItem } from "@/lib/portfolio";
import { formatCompact, formatCurrency, formatNumber, formatPercent } from "@/lib/formatters";
import type { Candle, Company } from "@/lib/types";

type PortfolioPrediction = {
  derived_parameters: {
    S: number;
    K: number;
    r: number;
    sigma: number;
    option_type: "call" | "put";
    num_paths: number;
    lookback_days: number;
  };
  predictions: {
    horizon_days: number;
    methods: {
      monte_carlo: { price: number };
      fosm: { price: number };
      pem: { price: number };
      taguchi: { price: number };
    };
    average_price: number;
  }[];
};

type StockSentiment = {
  source: string;
  trend_source: string;
  summary: {
    label: "Positive" | "Negative" | "Neutral";
    score: number;
    mentions: number;
    positive: number;
    neutral: number;
    negative: number;
  };
  mentions: {
    title: string;
    subreddit: string;
    url: string;
    score: number;
    comments: number;
    sentiment: "Positive" | "Negative" | "Neutral";
  }[];
};

type AnalysisTab = "market" | "pipeline" | "fundamentals" | "deep";
type FundamentalMode = "standard" | "deep";

function analysisModeForTab(tab: AnalysisTab): FundamentalMode {
  return tab === "deep" ? "deep" : "standard";
}

function analysisCacheKey(symbol: string, mode: FundamentalMode) {
  return `${symbol}:${mode}`;
}

function summarizePortfolio(items: PortfolioItem[]) {
  const counts = items.reduce(
    (acc, item) => {
      const status = (item.health_status || "Neutral").toLowerCase();
      acc.total += 1;
      if (status === "healthy") acc.healthy += 1;
      else if (status === "unhealthy") acc.unhealthy += 1;
      else acc.neutral += 1;
      return acc;
    },
    { total: 0, healthy: 0, unhealthy: 0, neutral: 0 }
  );

  const sectorCounts = new Map<string, number>();
  items.forEach((item) => {
    const sector = item.sector || "Unknown";
    sectorCounts.set(sector, (sectorCounts.get(sector) || 0) + 1);
  });

  const topSector = Array.from(sectorCounts.entries()).sort((left, right) => right[1] - left[1])[0] || ["Unknown", 0];
  const avgChange = items.length
    ? items.reduce((sum, item) => sum + (item.change_percent ?? 0), 0) / items.length
    : 0;

  return {
    ...counts,
    topSector: topSector[0],
    topSectorCount: topSector[1],
    avgChange
  };
}

function usableCandles(candles: Candle[]) {
  return candles.filter((candle) => candle.close !== null && candle.high !== null && candle.low !== null && candle.open !== null);
}

function PortfolioChart({ candles }: { candles: Candle[] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const points = usableCandles(candles).slice(-120);
  const width = 760;
  const height = 260;
  const padX = 38;
  const padY = 24;

  if (points.length < 2) {
    return <div className="grid h-[260px] place-items-center text-sm text-slate-400">No historical chart available.</div>;
  }

  const closes = points.map((point) => point.close as number);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const x = (index: number) => padX + (index / Math.max(points.length - 1, 1)) * (width - padX * 2);
  const y = (value: number) => padY + ((max - value) / Math.max(max - min, 1)) * (height - padY * 2);
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(point.close as number)}`).join(" ");
  const rising = closes[closes.length - 1] >= closes[0];
  const stroke = rising ? "#079b83" : "#d65a50";
  const hovered = hoverIndex === null ? null : points[hoverIndex];

  function handleMove(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const index = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
    setHoverIndex(index);
  }

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-[260px] w-full"
        role="img"
        aria-label="Portfolio stock price history"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {[0, 1, 2].map((line) => {
          const gy = padY + (line / 2) * (height - padY * 2);
          return <line key={line} x1={padX} x2={width - padX} y1={gy} y2={gy} stroke="#eef1f4" />;
        })}
        <path d={`${path} L ${width - padX} ${height - padY} L ${padX} ${height - padY} Z`} fill={rising ? "rgba(7,155,131,0.08)" : "rgba(214,90,80,0.08)"} />
        <path d={path} fill="none" stroke={stroke} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {hovered && (
          <g>
            <line x1={x(hoverIndex as number)} x2={x(hoverIndex as number)} y1={padY} y2={height - padY} stroke="#94a3b8" strokeDasharray="4 4" />
            <circle cx={x(hoverIndex as number)} cy={y(hovered.close as number)} r="4" fill={stroke} stroke="#fff" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hovered && (
        <div
          className="pointer-events-none absolute z-20 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg"
          style={{
            left: `${Math.min(78, Math.max(6, (x(hoverIndex as number) / width) * 100))}%`,
            top: `${Math.max(6, Math.min(74, (y(hovered.close as number) / height) * 100))}%`
          }}
        >
          <div className="font-semibold text-slate-700">{hovered.date}</div>
          <div className="mt-1 font-mono text-slate-500">{formatCurrency(hovered.close)}</div>
        </div>
      )}
    </div>
  );
}

function combinePortfolioCandles(items: PortfolioItem[]): Candle[] {
  const byDate = new Map<string, Candle>();

  items.forEach((item) => {
    usableCandles(item.stock_snapshot?.candles ?? []).forEach((candle) => {
      const current = byDate.get(candle.date) ?? {
        date: candle.date,
        open: 0,
        high: 0,
        low: 0,
        close: 0,
        volume: 0
      };

      byDate.set(candle.date, {
        date: candle.date,
        open: (current.open ?? 0) + (candle.open ?? 0),
        high: (current.high ?? 0) + (candle.high ?? 0),
        low: (current.low ?? 0) + (candle.low ?? 0),
        close: (current.close ?? 0) + (candle.close ?? 0),
        volume: (current.volume ?? 0) + (candle.volume ?? 0)
      });
    });
  });

  return Array.from(byDate.values()).sort((left, right) => left.date.localeCompare(right.date));
}

function buildAggregateSnapshot(items: PortfolioItem[]): Company | null {
  if (items.length === 0) return null;

  const candles = combinePortfolioCandles(items);
  const price = items.reduce((sum, item) => sum + (item.spot_price ?? item.price ?? 0), 0);
  const previousClose = items.reduce((sum, item) => sum + (item.previous_close ?? 0), 0);
  const change = previousClose ? price - previousClose : null;

  return {
    symbol: "PORTFOLIO",
    ticker: "PORTFOLIO",
    name: "Overall Portfolio",
    sector: "Combined holdings",
    marketCap: items.reduce((sum, item) => sum + (item.market_cap ?? 0), 0),
    price,
    change,
    changePercent: previousClose && change !== null ? (change / previousClose) * 100 : null,
    open: items.reduce((sum, item) => sum + (item.open ?? 0), 0),
    high: items.reduce((sum, item) => sum + (item.high ?? 0), 0),
    low: items.reduce((sum, item) => sum + (item.low ?? 0), 0),
    previousClose,
    volume: items.reduce((sum, item) => sum + (item.volume ?? 0), 0),
    candles
  };
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-200 bg-white/80 p-3 shadow-sm">
      <div className="text-xs font-medium uppercase text-slate-400">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold text-slate-800">{value}</div>
    </div>
  );
}

function impliedStockPrice(prediction: PortfolioPrediction, methodPrice: number) {
  const { K, option_type } = prediction.derived_parameters;
  return option_type === "put" ? Math.max(0, K - methodPrice) : K + methodPrice;
}

function predictionDirection(prediction: PortfolioPrediction, averageStockPrice: number) {
  return averageStockPrice >= prediction.derived_parameters.S ? "up" : "down";
}

async function readApiJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  const contentType = response.headers.get("content-type") || "";

  if (!contentType.includes("application/json")) {
    const text = await response.text();
    const message = text.includes("Cannot find module")
      ? "The local Next.js build cache is stale. Restart the dev server and refresh the page."
      : fallbackMessage;

    throw new Error(message);
  }

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || fallbackMessage);
  }

  return data as T;
}

export function PortfolioClient() {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [prediction, setPrediction] = useState<PortfolioPrediction | null>(null);
  const [predictionError, setPredictionError] = useState<string | null>(null);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [sentiment, setSentiment] = useState<StockSentiment | null>(null);
  const [sentimentError, setSentimentError] = useState<string | null>(null);
  const [sentimentLoading, setSentimentLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [removingSymbol, setRemovingSymbol] = useState<string | null>(null);

  // Advanced AI Pipeline States
  const [activeTab, setActiveTab] = useState<AnalysisTab>("market");
  const [analysisData, setAnalysisData] = useState<Record<string, any>>({});
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [loadingMessageIdx, setLoadingMessageIdx] = useState(0);

  const loadingMessages = [
    "Activating Numeric Engine (Tier 0)...",
    "Fetching market data and peer statistics...",
    "Running Quantitative Synthesizer (Tier 1A)...",
    "Analyzing factor regressions and solvency ratios...",
    "Gathering latest news & earnings call transcripts...",
    "Running Narrative Synthesizer (Tier 1B)...",
    "Integrating raw market structure metrics (Tier 1C)...",
    "Synthesizing final signals with General Expert (Tier 2)..."
  ];

  const fetchAnalysis = async (symbol: string, forceRefresh: boolean = false, mode: FundamentalMode = "standard") => {
    if (!symbol) return;
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const response = await fetch("/api/portfolio/analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, force_refresh: forceRefresh, mode })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Failed to fetch analysis.");
      }
      setAnalysisData((prev) => ({
        ...prev,
        [analysisCacheKey(symbol, mode)]: data
      }));
    } catch (err: any) {
      setAnalysisError(err.message || "An unexpected error occurred.");
    } finally {
      setAnalysisLoading(false);
    }
  };

  // Reset the response view when the selection changes.
  useEffect(() => {
    setActiveTab(selectedSymbol ? "fundamentals" : "market");
  }, [selectedSymbol]);

  // Loading message rotator
  useEffect(() => {
    let interval: any;
    if (analysisLoading) {
      interval = setInterval(() => {
        setLoadingMessageIdx((prev) => (prev + 1) % loadingMessages.length);
      }, 3000);
    } else {
      setLoadingMessageIdx(0);
    }
    return () => clearInterval(interval);
  }, [analysisLoading]);

  useEffect(() => {
    getPortfolioItems().then(({ items: portfolioItems, error }) => {
      setItems(portfolioItems);
      setSelectedSymbol(null);
      setMessage(error);
      setLoading(false);
    });
  }, []);

  const summary = useMemo(() => {
    const investedValue = items.reduce((total, item) => total + (item.price ?? 0), 0);
    const gainers = items.filter((item) => (item.change_percent ?? 0) >= 0).length;
    return { investedValue, gainers };
  }, [items]);

  const selectedItem = useMemo(() => {
    return selectedSymbol ? items.find((item) => item.symbol === selectedSymbol) ?? null : null;
  }, [items, selectedSymbol]);

  const aggregateSnapshot = useMemo(() => buildAggregateSnapshot(items), [items]);

  const activeView = useMemo(() => {
    if (selectedItem) {
      return {
        symbol: selectedItem.symbol,
        name: selectedItem.name,
        subtitle: `${selectedItem.sector ?? "Stock"} - ${selectedItem.index_name ?? "Portfolio"}`,
        price: selectedItem.spot_price ?? selectedItem.price,
        change: selectedItem.change,
        changePercent: selectedItem.change_percent,
        strike: selectedItem.strike_price,
        riskFreeRate: selectedItem.risk_free_rate,
        snapshot: selectedItem.stock_snapshot,
        isOverall: false
      };
    }

    if (!aggregateSnapshot) return null;

    return {
      symbol: "PORTFOLIO",
      name: "Overall Portfolio",
      subtitle: `${items.length} combined holdings`,
      price: aggregateSnapshot.price,
      change: aggregateSnapshot.change,
      changePercent: aggregateSnapshot.changePercent,
      strike: aggregateSnapshot.price,
      riskFreeRate: 0.05,
      snapshot: aggregateSnapshot,
      isOverall: true
    };
  }, [aggregateSnapshot, items.length, selectedItem]);

  // Fetch analysis data when a symbol and tab are selected
  useEffect(() => {
    if (!activeView || activeView.isOverall) return;
    const mode = analysisModeForTab(activeTab);
    const cacheKey = analysisCacheKey(activeView.symbol, mode);
    if (
      (activeTab === "pipeline" || activeTab === "fundamentals" || activeTab === "deep") &&
      !analysisData[cacheKey] &&
      !analysisLoading
    ) {
      fetchAnalysis(activeView.symbol, false, mode);
    }
  }, [activeTab, activeView, analysisData, analysisLoading]);

  useEffect(() => {
    if (!activeView) {
      setPrediction(null);
      return;
    }

    let active = true;
    setPredictionLoading(true);
    setPredictionError(null);

    fetch("/api/portfolio/predict", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        symbol: activeView.symbol,
        name: activeView.name,
        price: activeView.price,
        strike_price: activeView.strike,
        risk_free_rate: activeView.riskFreeRate,
        option_type: "call",
        num_paths: 10000,
        stock_snapshot: activeView.snapshot
      })
    })
      .then(async (response) => {
        return readApiJson<PortfolioPrediction>(response, "Prediction failed.");
      })
      .then((data) => {
        if (active) setPrediction(data);
      })
      .catch((error: Error) => {
        if (active) {
          setPrediction(null);
          setPredictionError(error.message);
        }
      })
      .finally(() => {
        if (active) setPredictionLoading(false);
      });

    return () => {
      active = false;
    };
  }, [activeView]);

  useEffect(() => {
    if (!selectedItem) {
      setSentiment(null);
      return;
    }

    let active = true;
    setSentimentLoading(true);
    setSentimentError(null);

    fetch("/api/portfolio/sentiment", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        symbol: selectedItem.symbol,
        ticker: selectedItem.ticker,
        name: selectedItem.name
      })
    })
      .then(async (response) => {
        return readApiJson<StockSentiment>(response, "Sentiment fetch failed.");
      })
      .then((data) => {
        if (active) setSentiment(data);
      })
      .catch((error: Error) => {
        if (active) {
          setSentiment(null);
          setSentimentError(error.message);
        }
      })
      .finally(() => {
        if (active) setSentimentLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedItem]);

  async function handleRemove(symbol: string) {
    setRemovingSymbol(symbol);
    const { error } = await removePortfolioItem(symbol);
    setRemovingSymbol(null);

    if (error) {
      setMessage(error);
      return;
    }

    setItems((current) => {
      const next = current.filter((item) => item.symbol !== symbol);
      if (selectedSymbol === symbol) setSelectedSymbol(null);
      return next;
    });
    setMessage(`${symbol} removed from portfolio.`);
  }

  const activeAnalysisMode = analysisModeForTab(activeTab);
  const activeAnalysis = activeView && !activeView.isOverall
    ? analysisData[analysisCacheKey(activeView.symbol, activeAnalysisMode)]
    : null;
  const portfolioOverview = useMemo(() => summarizePortfolio(items), [items]);

  return (
    <main className="soft-page min-h-screen px-4 py-5 text-slate-700 md:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4">
          <div>
            <Link href="/dashboard" className="mb-2 inline-flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-slate-900">
              <ArrowLeft className="h-4 w-4" />
              Dashboard
            </Link>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">User Portfolio</div>
            <h1 className="mt-1 text-2xl font-semibold text-slate-800">Selected Stocks</h1>
          </div>
          <ProfileMenu />
        </header>

        <section className="mb-5 grid gap-4 md:grid-cols-3">
          <article className="surface-card rounded-lg border p-4">
            <div className="text-sm text-slate-400">Stocks added</div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-800">{items.length}</div>
          </article>
          <article className="surface-card rounded-lg border p-4">
            <div className="text-sm text-slate-400">Combined latest price</div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-800">{formatCurrency(summary.investedValue)}</div>
          </article>
          <article className="surface-card rounded-lg border p-4">
            <div className="text-sm text-slate-400">Positive movers</div>
            <div className="mt-2 font-mono text-2xl font-semibold text-emerald-600">{summary.gainers}</div>
          </article>
        </section>

        {message && (
          <div className="mb-5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
            {message}
          </div>
        )}

        {activeView && (
          <section className="mb-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="surface-panel rounded-lg border">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
                <div>
                  <div className="font-mono text-sm text-slate-500">{activeView.symbol}</div>
                  <h2 className="mt-1 text-xl font-semibold text-slate-800">{activeView.name}</h2>
                  <p className="mt-1 text-sm text-slate-400">{activeView.subtitle}</p>
                </div>
                <div className="text-right">
                  <div className="font-mono text-2xl font-semibold text-slate-800">{formatCurrency(activeView.price)}</div>
                  <div className={`font-mono text-sm font-semibold ${(activeView.changePercent ?? 0) >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                    {formatNumber(activeView.change)} ({formatPercent(activeView.changePercent)})
                  </div>
                </div>
              </div>
              {!activeView.isOverall && (
                <div className="flex border-b border-slate-200 bg-slate-50/50 px-5">
                  {[
                    { id: "market", label: "Market & Option Pricing" },
                    { id: "pipeline", label: "AI Pipeline Analysis" },
                    { id: "fundamentals", label: "Fundamental Analysis" },
                    { id: "deep", label: "Deep Analysis" }
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id as AnalysisTab)}
                      className={`border-b-2 px-4 py-3 text-sm font-semibold transition-colors -mb-[2px] ${
                        activeTab === tab.id
                          ? "border-emerald-600 text-emerald-700"
                          : "border-transparent text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              )}

              {/* Tab Content */}
              {activeTab === "market" || activeView.isOverall ? (
                <>
                  <div className="px-4 py-3">
                    <PortfolioChart candles={activeView.snapshot?.candles ?? []} />
                  </div>
                  <div className="border-t border-slate-200 px-4 py-4">
                    <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Predicted Option Price</h2>
                    {predictionLoading ? (
                      <div className="rounded border border-slate-200 bg-white/80 px-3 py-4 text-sm text-slate-500">
                        Calculating method predictions...
                      </div>
                    ) : predictionError ? (
                      <div className="rounded border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800">
                        {predictionError}
                      </div>
                    ) : prediction ? (
                      <div className="grid gap-3 md:grid-cols-3">
                        {prediction.predictions.map((row) => {
                          const methodPrices = {
                            monte_carlo: impliedStockPrice(prediction, row.methods.monte_carlo.price),
                            fosm: impliedStockPrice(prediction, row.methods.fosm.price),
                            pem: impliedStockPrice(prediction, row.methods.pem.price),
                            taguchi: impliedStockPrice(prediction, row.methods.taguchi.price)
                          };
                          const averageStockPrice =
                            (methodPrices.monte_carlo + methodPrices.fosm + methodPrices.pem + methodPrices.taguchi) / 4;
                          const direction = predictionDirection(prediction, averageStockPrice);

                          return (
                            <div key={row.horizon_days} className="rounded border border-slate-200 bg-white/85 p-3 shadow-sm">
                              <div className="mb-3 flex items-center justify-between">
                                <span className="text-sm font-semibold text-slate-700">Day {row.horizon_days}</span>
                                <span className={`inline-flex items-center gap-1 font-mono text-lg font-semibold ${direction === "up" ? "text-emerald-700" : "text-red-600"}`}>
                                  {direction === "up" ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
                                  {formatCurrency(averageStockPrice)}
                                </span>
                              </div>
                              <div className="grid grid-cols-2 gap-2 text-xs text-slate-600">
                                <span className="rounded bg-slate-50 px-2 py-1">MC {formatCurrency(methodPrices.monte_carlo)}</span>
                                <span className="rounded bg-slate-50 px-2 py-1">FOSM {formatCurrency(methodPrices.fosm)}</span>
                                <span className="rounded bg-slate-50 px-2 py-1">PEM {formatCurrency(methodPrices.pem)}</span>
                                <span className="rounded bg-slate-50 px-2 py-1">Taguchi {formatCurrency(methodPrices.taguchi)}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="rounded border border-slate-200 bg-white/80 px-3 py-4 text-sm text-slate-500">
                        Select a portfolio stock to calculate predictions.
                      </div>
                    )}
                  </div>
                </>
              ) : analysisLoading ? (
                <div className="flex flex-col items-center justify-center py-16 px-4">
                  <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-600"></div>
                  <p className="mt-4 text-sm font-medium text-slate-600 animate-pulse text-center">
                    {loadingMessages[loadingMessageIdx]}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    This runs the live multi-agent pipeline and can take 15-30s.
                  </p>
                </div>
              ) : analysisError ? (
                <div className="p-5">
                  <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
                      <div>
                        <h3 className="text-sm font-semibold text-red-800">Analysis Run Failed</h3>
                        <p className="mt-1 text-sm text-red-700">{analysisError}</p>
                        <button
                          type="button"
                          onClick={() => fetchAnalysis(activeView.symbol, true, activeAnalysisMode)}
                          className="mt-3 inline-flex items-center gap-1.5 rounded border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                          Retry Running Pipeline
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : !activeAnalysis ? (
                <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
                  <Sparkles className="h-8 w-8 text-slate-300 animate-pulse" />
                  <h3 className="mt-3 text-sm font-semibold text-slate-700">No Analysis Available</h3>
                  <p className="mt-1 text-xs text-slate-400 max-w-xs">
                    Run the {activeAnalysisMode === "deep" ? "deep" : "multi-tier MoE"} analysis pipeline to synthesize quantitative metrics and qualitative reports.
                  </p>
                  <button
                    type="button"
                    onClick={() => fetchAnalysis(activeView.symbol, false, activeAnalysisMode)}
                    className="mt-4 inline-flex items-center gap-1.5 rounded bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 shadow transition-colors"
                  >
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    Run Pipeline Analysis
                  </button>
                </div>
              ) : activeTab === "pipeline" ? (
                // AI Pipeline Analysis View
                (() => {
                  const symbolData = activeAnalysis;
                  const pipeline = symbolData.pipeline || {};
                  const signals = pipeline.signals || {};
                  const tactical = signals.tactical_horizon_30d || {};
                  const structural = signals.structural_horizon_1y || {};
                  
                  const getDirectionBadgeClass = (dir: string) => {
                    const d = dir?.toLowerCase();
                    if (d === "bullish") return "bg-emerald-100 text-emerald-800 border-emerald-200";
                    if (d === "bearish") return "bg-rose-100 text-rose-800 border-rose-200";
                    return "bg-slate-100 text-slate-800 border-slate-200";
                  };

                  return (
                    <div className="px-5 py-4 space-y-5">
                      {symbolData.fallback && (
                        <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-800 flex items-start gap-2 shadow-sm">
                          <AlertTriangle className="h-4.5 w-4.5 text-amber-600 shrink-0 mt-0.5 animate-pulse" />
                          <div>
                            {symbolData.fallbackReason === "failed" ? (
                              <>
                                <span className="font-bold">AI Pipeline Rate-Limited / Failed:</span> The Python analysis server (port 8765) is online, but the backend API call failed (e.g. Gemini API quota limits exceeded). Showing high-fidelity simulated analysis. Check your terminal/server logs.
                              </>
                            ) : (
                              <>
                                <span className="font-bold">FastAPI Backend Offline:</span> The Python analysis server (port 8765) is offline. Showing high-fidelity simulated analysis. Run <code>uvicorn pipeline.api:app --host 127.0.0.1 --port 8765</code> to connect the live agents.
                              </>
                            )}
                          </div>
                        </div>
                      )}

                      <div className="flex justify-between items-center pb-2 border-b border-slate-100">
                        <div className="flex items-center gap-2">
                          <Sparkles className="h-4.5 w-4.5 text-emerald-600" />
                          <h3 className="text-sm font-semibold text-slate-800">Advanced Mixture of Experts (MoE) Signals</h3>
                        </div>
                        <button
                          type="button"
                          onClick={() => fetchAnalysis(activeView.symbol, true, "standard")}
                          className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors shadow-sm"
                        >
                          <RefreshCw className="h-3 w-3" />
                          Re-run Pipeline
                        </button>
                      </div>

                      {/* Signals Columns */}
                      <div className="grid gap-4 md:grid-cols-2">
                        {/* Tactical Signal */}
                        <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm flex flex-col justify-between">
                          <div>
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Short-Term Tactical (30d)</h4>
                              <span className={`px-2 py-0.5 rounded text-[11px] font-bold border uppercase ${getDirectionBadgeClass(tactical.direction)}`}>
                                {tactical.direction || "neutral"}
                              </span>
                            </div>
                            
                            <div className="mt-3">
                              <div className="flex justify-between text-[11px] font-medium text-slate-500 mb-1">
                                <span>Signal Confidence</span>
                                <span>{Math.round((tactical.confidence || 0.5) * 100)}%</span>
                              </div>
                              <div className="w-full bg-slate-100 rounded-full h-1.5">
                                <div
                                  className={`h-1.5 rounded-full ${
                                    tactical.direction === "bullish" ? "bg-emerald-600" : tactical.direction === "bearish" ? "bg-rose-500" : "bg-slate-400"
                                  }`}
                                  style={{ width: `${(tactical.confidence || 0.5) * 100}%` }}
                                ></div>
                              </div>
                            </div>

                            {/* Pros */}
                            <div className="mt-4 space-y-1">
                              <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Supporting Factors</h5>
                              <ul className="space-y-1">
                                {(tactical.corroborating_signals || []).map((sig: string, idx: number) => (
                                  <li key={idx} className="text-xs text-slate-600 flex items-start gap-1.5 leading-snug">
                                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0 mt-0.5" />
                                    <span>{sig}</span>
                                  </li>
                                ))}
                                {(!tactical.corroborating_signals || tactical.corroborating_signals.length === 0) && (
                                  <li className="text-xs text-slate-400 italic">No short-term catalysts detected.</li>
                                )}
                              </ul>
                            </div>
                          </div>

                          {/* Cons */}
                          <div className="mt-4 border-t border-slate-100 pt-3 space-y-1">
                            <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Risks & Counter-Arguments</h5>
                            <ul className="space-y-1">
                              {(tactical.contradicting_signals || []).map((sig: string, idx: number) => (
                                <li key={idx} className="text-xs text-slate-600 flex items-start gap-1.5 leading-snug">
                                  <XCircle className="h-3.5 w-3.5 text-rose-500 shrink-0 mt-0.5" />
                                  <span>{sig}</span>
                                </li>
                              ))}
                              {(!tactical.contradicting_signals || tactical.contradicting_signals.length === 0) && (
                                <li className="text-xs text-slate-400 italic">No significant headwinds noted.</li>
                              )}
                            </ul>
                          </div>
                        </div>

                        {/* Structural Signal */}
                        <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm flex flex-col justify-between">
                          <div>
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Long-Term Structural (1y)</h4>
                              <span className={`px-2 py-0.5 rounded text-[11px] font-bold border uppercase ${getDirectionBadgeClass(structural.direction)}`}>
                                {structural.direction || "neutral"}
                              </span>
                            </div>
                            
                            <div className="mt-3">
                              <div className="flex justify-between text-[11px] font-medium text-slate-500 mb-1">
                                <span>Signal Confidence</span>
                                <span>{Math.round((structural.confidence || 0.5) * 100)}%</span>
                              </div>
                              <div className="w-full bg-slate-100 rounded-full h-1.5">
                                <div
                                  className={`h-1.5 rounded-full ${
                                    structural.direction === "bullish" ? "bg-emerald-600" : structural.direction === "bearish" ? "bg-rose-500" : "bg-slate-400"
                                  }`}
                                  style={{ width: `${(structural.confidence || 0.5) * 100}%` }}
                                ></div>
                              </div>
                            </div>

                            {/* Pros */}
                            <div className="mt-4 space-y-1">
                              <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Supporting Factors</h5>
                              <ul className="space-y-1">
                                {(structural.corroborating_signals || []).map((sig: string, idx: number) => (
                                  <li key={idx} className="text-xs text-slate-600 flex items-start gap-1.5 leading-snug">
                                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 shrink-0 mt-0.5" />
                                    <span>{sig}</span>
                                  </li>
                                ))}
                                {(!structural.corroborating_signals || structural.corroborating_signals.length === 0) && (
                                  <li className="text-xs text-slate-400 italic">No structural catalysts detected.</li>
                                )}
                              </ul>
                            </div>
                          </div>

                          {/* Cons */}
                          <div className="mt-4 border-t border-slate-100 pt-3 space-y-1">
                            <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Risks & Counter-Arguments</h5>
                            <ul className="space-y-1">
                              {(structural.contradicting_signals || []).map((sig: string, idx: number) => (
                                <li key={idx} className="text-xs text-slate-600 flex items-start gap-1.5 leading-snug">
                                  <XCircle className="h-3.5 w-3.5 text-rose-500 shrink-0 mt-0.5" />
                                  <span>{sig}</span>
                                </li>
                              ))}
                              {(!structural.contradicting_signals || structural.contradicting_signals.length === 0) && (
                                <li className="text-xs text-slate-400 italic">No significant headwinds noted.</li>
                              )}
                            </ul>
                          </div>
                        </div>
                      </div>

                      {/* General Expert Rationale */}
                      <div className="rounded-lg border border-slate-100 bg-slate-50/40 p-4">
                        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">General Expert Synthesis</h4>
                        <p className="text-xs leading-relaxed text-slate-600">{pipeline.rationale || "No summary rationale compiled."}</p>
                      </div>

                      {/* Macro regime / adjustments */}
                      {pipeline.macro_regime_adjustment && (
                        <div className="rounded-lg border border-blue-100 bg-blue-50/40 p-3 text-xs text-slate-600 flex gap-2">
                          <Info className="h-4 w-4 text-blue-600 shrink-0 mt-0.5" />
                          <div>
                            <span className="font-semibold text-blue-800">Macro Adjustment: </span>
                            {pipeline.macro_regime_adjustment}
                          </div>
                        </div>
                      )}

                      {/* Consistency flags */}
                      {pipeline.consistency_flags && pipeline.consistency_flags.length > 0 && (
                        <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-3 text-xs text-slate-600">
                          <div className="font-semibold text-amber-800 flex items-center gap-1.5 mb-1">
                            <AlertTriangle className="h-4.5 w-4.5 text-amber-600 shrink-0" />
                            Upstream Semantic Consistency Warnings
                          </div>
                          <ul className="list-disc pl-5 mt-1 space-y-0.5 text-slate-500">
                            {pipeline.consistency_flags.map((flag: string, idx: number) => (
                              <li key={idx}>{flag}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Technical and Data Quality */}
                      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-400 pt-1">
                        <span className="flex items-center gap-1">
                          <ShieldAlert className="h-3.5 w-3.5" />
                          Pipeline Data Quality Score: <strong>{Math.round((pipeline.data_quality_score || 1) * 100)}%</strong>
                        </span>
                        <span className="flex items-center gap-1">
                          <Activity className="h-3.5 w-3.5" />
                          Overall Model Confidence: <strong>{Math.round((pipeline.overall_confidence || 0.5) * 100)}%</strong>
                        </span>
                      </div>
                    </div>
                  );
                })()
              ) : (
                // Fundamental Health View
                (() => {
                  const symbolData = activeAnalysis;
                  const fundamentals = symbolData.fundamentals || {};
                  const scores = fundamentals.dimension_scores || {};
                  const peer = fundamentals.peer_comparison || {};
                  const smart = fundamentals.smart_money_read || {};
                  const risks = fundamentals.risk_assessment || {};
                  const sourceData = fundamentals.source_data || {};
                  const factor = sourceData.factor_exposure || {};
                  const options = sourceData.options_signals || {};
                  const quality = sourceData.data_quality || {};
                  const isDeepAnalysis = activeTab === "deep";

                  const getScoreBadgeClass = (score: string) => {
                    const s = score?.toLowerCase() || "";
                    if (s === "strong" || s === "attractive") return "bg-emerald-100 text-emerald-800 border-emerald-200";
                    if (s === "weak" || s === "expensive") return "bg-rose-100 text-rose-800 border-rose-200";
                    return "bg-slate-100 text-slate-800 border-slate-200";
                  };

                  return (
                    <div className="px-5 py-4 space-y-5">
                      {/* Verdict Banner */}
                      <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                        <div className="flex items-center gap-2 mb-2">
                          <Scale className="h-4.5 w-4.5 text-emerald-600" />
                          <h3 className="text-sm font-semibold text-slate-800">
                            {isDeepAnalysis ? "Deep Fundamental Scorecard" : "Fundamental Scorecard"}
                          </h3>
                        </div>
                        <div className="text-xs font-bold text-emerald-800 bg-emerald-50/70 border border-emerald-100 rounded px-3 py-2 leading-relaxed">
                          {fundamentals.one_line_verdict}
                        </div>
                        <p className="mt-3 text-xs text-slate-500 leading-relaxed">
                          {fundamentals.executive_summary}
                        </p>
                      </div>

                      {isDeepAnalysis && (
                        <div>
                          <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Deep Mode Signals</h4>
                          <div className="grid gap-4 md:grid-cols-3">
                            <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                              <h5 className="text-xs font-semibold text-slate-800 border-b border-slate-100 pb-2 mb-3">Factor Exposure</h5>
                              <dl className="space-y-2 text-xs">
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Annualized Alpha</dt><dd className="font-mono text-slate-700">{formatNumber(factor.alpha_annualized)}</dd></div>
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Market Beta</dt><dd className="font-mono text-slate-700">{formatNumber(factor.market_beta)}</dd></div>
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Momentum Loading</dt><dd className="font-mono text-slate-700">{formatNumber(factor.momentum_loading)}</dd></div>
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">R Squared</dt><dd className="font-mono text-slate-700">{formatNumber(factor.r_squared)}</dd></div>
                              </dl>
                            </div>
                            <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                              <h5 className="text-xs font-semibold text-slate-800 border-b border-slate-100 pb-2 mb-3">Options Market</h5>
                              <dl className="space-y-2 text-xs">
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">IV Rank</dt><dd className="font-mono text-slate-700">{formatNumber(options.iv_rank)}</dd></div>
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Put/Call Volume</dt><dd className="font-mono text-slate-700">{formatNumber(options.put_call_ratio_volume)}</dd></div>
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Term Structure</dt><dd className="font-semibold text-slate-700">{options.term_structure || "NA"}</dd></div>
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Event Risk</dt><dd className="font-semibold text-slate-700">{options.near_term_event_risk ? "Yes" : "No"}</dd></div>
                              </dl>
                            </div>
                            <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                              <h5 className="text-xs font-semibold text-slate-800 border-b border-slate-100 pb-2 mb-3">Data Coverage</h5>
                              <dl className="space-y-2 text-xs">
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Mode</dt><dd className="font-semibold uppercase text-slate-700">{sourceData.mode || "deep"}</dd></div>
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Fields</dt><dd className="font-mono text-slate-700">{quality.fields_received ?? "NA"} / {quality.fields_requested ?? "NA"}</dd></div>
                                <div className="flex justify-between gap-3"><dt className="text-slate-400">Quality</dt><dd className="font-mono text-slate-700">{formatNumber(quality.quality_score)}</dd></div>
                              </dl>
                              {quality.fields_missing?.length > 0 && (
                                <p className="mt-3 text-[10px] leading-snug text-amber-700">
                                  Missing: {quality.fields_missing.join(", ")}
                                </p>
                              )}
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Dimension Scores Grid */}
                      <div>
                        <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Dimension Scores</h4>
                        <div className="grid gap-3 grid-cols-2 sm:grid-cols-5">
                          {Object.entries(scores).map(([key, dim]: any) => {
                            const title = key.replace(/_/g, " ");
                            return (
                              <div key={key} className="rounded-lg border border-slate-200 bg-white/80 p-3 shadow-sm flex flex-col justify-between">
                                <div>
                                  <h5 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider truncate mb-1" title={title}>{title}</h5>
                                  <span className={`inline-block px-2 py-0.5 rounded text-[9px] font-extrabold uppercase border ${getScoreBadgeClass(dim.score)}`}>
                                    {dim.score}
                                  </span>
                                </div>
                                <p className="mt-2 text-[10px] text-slate-500 leading-snug">{dim.rationale}</p>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Peer Comparison and Smart Money */}
                      <div className="grid gap-4 md:grid-cols-2">
                        {/* Peer Comparison */}
                        <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                          <h4 className="text-xs font-semibold text-slate-800 border-b border-slate-100 pb-2 mb-3">Peer & Moat Delta</h4>
                          <div className="space-y-3">
                            <div>
                              <div className="text-[10px] text-slate-400 uppercase font-semibold">Overall Standing</div>
                              <span className={`mt-1 inline-block px-2.5 py-0.5 rounded text-[10px] font-bold border uppercase bg-slate-55 text-slate-600 border-slate-200`}>
                                {peer.overall_peer_standing || "in-line"}
                              </span>
                            </div>
                            <div className="text-xs text-slate-600 space-y-2">
                              <p className="flex items-start gap-1.5">
                                <span className="h-1.5 w-1.5 bg-slate-400 rounded-full mt-1.5 shrink-0"></span>
                                <span>{peer.gross_margin_vs_peers}</span>
                              </p>
                              <p className="flex items-start gap-1.5">
                                <span className="h-1.5 w-1.5 bg-slate-400 rounded-full mt-1.5 shrink-0"></span>
                                <span>{peer.current_ratio_vs_peers}</span>
                              </p>
                            </div>
                          </div>
                        </div>

                        {/* Smart Money Read */}
                        <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                          <h4 className="text-xs font-semibold text-slate-800 border-b border-slate-100 pb-2 mb-3">Smart Money Activity</h4>
                          <div className="space-y-3">
                            <div className="flex gap-4">
                              <div>
                                <div className="text-[10px] text-slate-400 uppercase font-semibold">Insider Signal</div>
                                <span className={`mt-1 inline-block px-2 py-0.5 rounded text-[9px] font-extrabold uppercase border ${getScoreBadgeClass(smart.insider_signal === "bullish" ? "strong" : smart.insider_signal === "bearish" ? "weak" : "neutral")}`}>
                                  {smart.insider_signal}
                                </span>
                              </div>
                              <div>
                                <div className="text-[10px] text-slate-400 uppercase font-semibold">Inst. Flow</div>
                                <span className={`mt-1 inline-block px-2 py-0.5 rounded text-[9px] font-extrabold uppercase border ${getScoreBadgeClass(smart.institutional_signal === "accumulating" ? "strong" : smart.institutional_signal === "distributing" ? "weak" : "neutral")}`}>
                                  {smart.institutional_signal}
                                </span>
                              </div>
                            </div>
                            <p className="text-xs text-slate-600 leading-normal">{smart.rationale}</p>
                          </div>
                        </div>
                      </div>

                      {/* Risks Card */}
                      <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                        <div className="flex justify-between items-center border-b border-slate-100 pb-2 mb-3">
                          <h4 className="text-xs font-semibold text-slate-800">Risk Assessment</h4>
                          <span className={`px-2 py-0.5 rounded text-[9px] font-bold border uppercase ${
                            risks.severity === "high" ? "bg-rose-100 text-rose-800 border-rose-200" : risks.severity === "medium" ? "bg-amber-100 text-amber-800 border-amber-200" : "bg-slate-100 text-slate-800 border-slate-200"
                          }`}>
                            {risks.severity || "medium"} severity
                          </span>
                        </div>
                        <div className="grid gap-4 md:grid-cols-2">
                          <div>
                            <h5 className="text-[10px] font-bold text-rose-700 uppercase tracking-wider mb-2">Identified Flags</h5>
                            <ul className="space-y-1.5">
                              {(risks.identified_risks || []).map((risk: string, idx: number) => (
                                <li key={idx} className="text-xs text-slate-600 flex items-start gap-1.5 leading-snug">
                                  <span className="text-rose-500 font-bold shrink-0 mt-0.5">!</span>
                                  <span>{risk.replace(/_/g, " ")}</span>
                                </li>
                              ))}
                              {(!risks.identified_risks || risks.identified_risks.length === 0) && (
                                <li className="text-xs text-slate-400 italic">No significant risk flags active.</li>
                              )}
                            </ul>
                          </div>
                          <div>
                            <h5 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Mitigating Strengths</h5>
                            <ul className="space-y-1.5">
                              {(risks.mitigating_factors || []).map((fact: string, idx: number) => (
                                <li key={idx} className="text-xs text-slate-600 flex items-start gap-1.5 leading-snug">
                                  <span className="text-emerald-600 font-bold shrink-0 mt-0.5">✓</span>
                                  <span>{fact}</span>
                                </li>
                              ))}
                              {(!risks.mitigating_factors || risks.mitigating_factors.length === 0) && (
                                <li className="text-xs text-slate-400 italic">No key mitigators listed.</li>
                              )}
                            </ul>
                          </div>
                        </div>
                      </div>

                      {/* Macro and Dates */}
                      <div className="flex flex-wrap justify-between items-center gap-2 text-xs text-slate-400 pt-1">
                        <span>Analysis Date: <strong>{fundamentals.analysis_date}</strong></span>
                        <span className="flex items-center gap-1">
                          <Info className="h-3.5 w-3.5" />
                          Macro Fit Regime: <strong>{(fundamentals.macro_fit?.regime || "neutral_macro").replace(/_/g, " ")}</strong>
                        </span>
                      </div>
                    </div>
                  );
                })()
              )}
            </div>

            <aside className="space-y-5">
              <section className="surface-card rounded-lg border p-4">
                <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Sentiment Analysis <Activity className="h-4 w-4 text-slate-400" />
                </h2>
                {sentimentLoading ? (
                  <div className="rounded border border-slate-200 bg-white/80 px-3 py-4 text-sm text-slate-500">
                    Reading recent stock discussions...
                  </div>
                ) : sentimentError ? (
                  <div className="rounded border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-800">
                    {sentimentError}
                  </div>
                ) : sentiment ? (
                  <div className="space-y-4">
                    <div className="rounded border border-slate-200 bg-white/85 p-3 shadow-sm">
                      <div className="text-xs font-medium uppercase text-slate-400">Overall mood</div>
                      <div
                        className={`mt-1 text-2xl font-semibold ${
                          sentiment.summary.label === "Positive"
                            ? "text-emerald-700"
                            : sentiment.summary.label === "Negative"
                              ? "text-red-600"
                              : "text-slate-700"
                        }`}
                      >
                        {sentiment.summary.label}
                      </div>
                      <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                        <span className="rounded bg-emerald-50 px-2 py-2 text-emerald-700">{sentiment.summary.positive} Positive</span>
                        <span className="rounded bg-slate-50 px-2 py-2 text-slate-600">{sentiment.summary.neutral} Neutral</span>
                        <span className="rounded bg-red-50 px-2 py-2 text-red-600">{sentiment.summary.negative} Negative</span>
                      </div>
                    </div>

                    <div className="space-y-2">
                      {sentiment.mentions.map((mention) => (
                        <a
                          key={`${mention.url}-${mention.title}`}
                          href={mention.url}
                          target="_blank"
                          rel="noreferrer"
                          className="block rounded border border-slate-200 bg-white/85 p-3 text-sm shadow-sm hover:border-emerald-200 hover:bg-emerald-50/40"
                        >
                          <div className="line-clamp-2 font-medium text-slate-700">{mention.title}</div>
                          <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
                            <span>r/{mention.subreddit}</span>
                            <span>{mention.sentiment}</span>
                          </div>
                        </a>
                      ))}
                    </div>

                    <p className="text-xs leading-5 text-slate-400">
                      Based on recent Reddit posts for this stock. Google Trends/pytrends can be wired through a Python service when available.
                    </p>
                  </div>
                ) : (
                  <div className="rounded border border-slate-200 bg-white/80 px-3 py-4 text-sm text-slate-500">
                    Select a portfolio stock to load sentiment.
                  </div>
                )}
              </section>
              <section className="surface-card rounded-lg border p-4">
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  {activeView.isOverall ? "Portfolio Snapshot" : "Stock Snapshot"}
                </h2>
                <div className="grid grid-cols-2 gap-3">
                  <DetailMetric label={activeView.isOverall ? "Total Spot" : "Spot"} value={formatCurrency(activeView.price)} />
                  <DetailMetric label="Strike" value={formatNumber(activeView.strike)} />
                  <DetailMetric label="Risk-free" value={activeView.riskFreeRate === null ? "NA" : formatPercent((activeView.riskFreeRate ?? 0.05) * 100)} />
                  <DetailMetric label="Health" value={activeView.isOverall ? "Combined" : selectedItem?.health_status ?? selectedItem?.config?.healthStatus ?? "Neutral"} />
                </div>
              </section>
            </aside>
          </section>
        )}

        <section className="surface-panel rounded-lg border">
          <div className="border-b border-slate-200 px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-800">Portfolio holdings</h2>
                <p className="text-sm text-slate-400">Saved per user in Supabase for future computation and calculations.</p>
              </div>
              {items.length > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedSymbol(null)}
                  className={`h-9 rounded border px-3 text-sm font-semibold ${
                    selectedSymbol === null
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                  }`}
                >
                  Overall portfolio
                </button>
              )}
            </div>
          </div>

          {loading ? (
            <div className="p-5 text-sm text-slate-500">Loading portfolio...</div>
          ) : items.length === 0 ? (
            <div className="p-8 text-center">
              <h3 className="text-lg font-semibold text-slate-800">No stocks added yet</h3>
              <p className="mt-2 text-sm text-slate-500">Add stocks from the dashboard to build this portfolio.</p>
              <Link
                href="/dashboard"
                className="mt-5 inline-flex h-10 items-center rounded border border-slate-900 bg-slate-900 px-4 text-sm font-semibold text-white hover:bg-slate-800"
              >
                Browse stocks
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[920px] border-collapse text-left">
                <thead className="soft-table-head text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-5 py-3 font-semibold">Stock</th>
                    <th className="px-5 py-3 text-right font-semibold">Index</th>
                    <th className="px-5 py-3 text-right font-semibold">Price</th>
                    <th className="px-5 py-3 text-right font-semibold">Change</th>
                    <th className="px-5 py-3 text-right font-semibold">Volume</th>
                    <th className="px-5 py-3 text-right font-semibold">Market Cap</th>
                    <th className="px-5 py-3 text-right font-semibold">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr
                      key={item.id}
                      onClick={() => setSelectedSymbol(item.symbol)}
                      className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${
                        selectedItem?.symbol === item.symbol ? "bg-emerald-50/60" : ""
                      }`}
                    >
                      <td className="px-5 py-4">
                        <div className="font-semibold text-slate-800">{item.name}</div>
                        <div className="font-mono text-xs text-slate-400">{item.symbol}</div>
                      </td>
                      <td className="px-5 py-4 text-right text-sm font-medium text-slate-500">{item.index_name}</td>
                      <td className="px-5 py-4 text-right font-mono font-semibold">{formatCurrency(item.price)}</td>
                      <td className={`px-5 py-4 text-right font-mono ${(item.change_percent ?? 0) >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                        {formatNumber(item.change)} ({formatPercent(item.change_percent)})
                      </td>
                      <td className="px-5 py-4 text-right font-mono">{formatCompact(item.volume)}</td>
                      <td className="px-5 py-4 text-right font-mono">{formatCompact(item.market_cap)}</td>
                      <td className="px-5 py-4 text-right">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleRemove(item.symbol);
                          }}
                          disabled={removingSymbol === item.symbol}
                          aria-label={`Remove ${item.symbol}`}
                          title="Remove"
                          className="inline-grid h-9 w-9 place-items-center rounded border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-red-500 disabled:opacity-50"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="mt-5 surface-panel rounded-lg border">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-800">Analysis response</h2>
              <p className="text-sm text-slate-400">
                {selectedItem
                  ? `Live analysis for ${selectedItem.symbol} updates here as soon as you click the stock.`
                  : "Portfolio-level summary from the holdings already in this workspace."}
              </p>
            </div>
            {selectedItem && (
              <div className="flex flex-wrap border border-slate-200 bg-slate-50/70 p-1">
                {[
                  { id: "fundamentals", label: "Fundamental Analysis" },
                  { id: "deep", label: "Deep Analysis" },
                  { id: "pipeline", label: "Pipeline" },
                  { id: "market", label: "Market" }
                ].map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setActiveTab(tab.id as AnalysisTab)}
                    className={`px-3 py-2 text-xs font-semibold transition-colors ${
                      activeTab === tab.id
                        ? "bg-emerald-600 text-white"
                        : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="px-5 py-5">
            {selectedItem ? (
              !activeAnalysis ? (
                <div className="flex flex-col items-center justify-center py-10 text-center">
                  {analysisLoading ? (
                    <>
                      <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-600"></div>
                      <p className="mt-4 text-sm font-medium text-slate-600">{loadingMessages[loadingMessageIdx]}</p>
                      <p className="mt-1 text-xs text-slate-400">The analysis model is warming up on the selected holding.</p>
                    </>
                  ) : analysisError ? (
                    <>
                      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-left">
                        <div className="flex items-start gap-2">
                          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
                          <div>
                            <h3 className="text-sm font-semibold text-red-800">Analysis Failed</h3>
                            <p className="mt-1 text-sm text-red-700">{analysisError}</p>
                            <button
                              type="button"
                              onClick={() => fetchAnalysis(selectedItem.symbol, true, activeAnalysisMode)}
                              className="mt-3 inline-flex items-center gap-1.5 rounded border border-red-300 bg-white px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50"
                            >
                              <RefreshCw className="h-3.5 w-3.5" />
                              Retry
                            </button>
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-8 w-8 animate-pulse text-slate-300" />
                      <h3 className="mt-3 text-sm font-semibold text-slate-700">No analysis yet</h3>
                      <p className="mt-1 max-w-md text-xs text-slate-400">Click a tab or retry the pipeline to load the live analysis for this holding.</p>
                    </>
                  )}
                </div>
              ) : activeTab === "pipeline" ? (
                <div className="space-y-4">
                  {(() => {
                    const symbolData = activeAnalysis;
                    const pipeline = symbolData.pipeline || {};
                    const signals = pipeline.signals || {};
                    const tactical = signals.tactical_horizon_30d || {};
                    const structural = signals.structural_horizon_1y || {};

                    const getDirectionBadgeClass = (dir: string) => {
                      const d = dir?.toLowerCase();
                      if (d === "bullish") return "bg-emerald-100 text-emerald-800 border-emerald-200";
                      if (d === "bearish") return "bg-rose-100 text-rose-800 border-rose-200";
                      return "bg-slate-100 text-slate-800 border-slate-200";
                    };

                    return (
                      <>
                        <div className="flex items-center justify-between gap-3">
                          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Pipeline Analysis</h3>
                          <button
                            type="button"
                            onClick={() => fetchAnalysis(selectedItem.symbol, true, "standard")}
                            className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                          >
                            <RefreshCw className="h-3 w-3" />
                            Re-run
                          </button>
                        </div>
                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Short-Term Tactical (30d)</h4>
                              <span className={`rounded border px-2 py-0.5 text-[11px] font-bold uppercase ${getDirectionBadgeClass(tactical.direction)}`}>
                                {tactical.direction || "neutral"}
                              </span>
                            </div>
                            <p className="mt-3 text-xs text-slate-600">{tactical.corroborating_signals?.[0] || "No short-term catalyst supplied."}</p>
                          </div>
                          <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                            <div className="flex items-center justify-between">
                              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Long-Term Structural (1y)</h4>
                              <span className={`rounded border px-2 py-0.5 text-[11px] font-bold uppercase ${getDirectionBadgeClass(structural.direction)}`}>
                                {structural.direction || "neutral"}
                              </span>
                            </div>
                            <p className="mt-3 text-xs text-slate-600">{structural.corroborating_signals?.[0] || "No structural catalyst supplied."}</p>
                          </div>
                        </div>
                        <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-4">
                          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">General Expert Synthesis</h4>
                          <p className="mt-2 text-xs leading-relaxed text-slate-600">{pipeline.rationale || "No summary rationale compiled."}</p>
                        </div>
                      </>
                    );
                  })()}
                </div>
              ) : (
                <div className="space-y-5">
                  {(() => {
                    const symbolData = activeAnalysis;
                    const fundamentals = symbolData.fundamentals || {};
                    const scores = fundamentals.dimension_scores || {};
                    const peer = fundamentals.peer_comparison || {};
                    const smart = fundamentals.smart_money_read || {};
                    const risks = fundamentals.risk_assessment || {};
                    const sourceData = fundamentals.source_data || {};
                    const factor = sourceData.factor_exposure || {};
                    const options = sourceData.options_signals || {};
                    const quality = sourceData.data_quality || {};
                    const isDeepAnalysis = activeTab === "deep";

                    const getScoreBadgeClass = (score: string) => {
                      const s = score?.toLowerCase() || "";
                      if (s === "strong" || s === "attractive") return "bg-emerald-100 text-emerald-800 border-emerald-200";
                      if (s === "weak" || s === "expensive") return "bg-rose-100 text-rose-800 border-rose-200";
                      return "bg-slate-100 text-slate-800 border-slate-200";
                    };

                    return (
                      <>
                        <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                          <div className="flex items-center gap-2">
                            <Scale className="h-4.5 w-4.5 text-emerald-600" />
                            <h3 className="text-sm font-semibold text-slate-800">{isDeepAnalysis ? "Deep Fundamental Scorecard" : "Fundamental Scorecard"}</h3>
                          </div>
                          <div className="mt-3 rounded border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs font-bold leading-relaxed text-emerald-800">
                            {fundamentals.one_line_verdict || "No verdict available."}
                          </div>
                          <p className="mt-3 text-xs leading-relaxed text-slate-500">{fundamentals.executive_summary || "No summary available."}</p>
                        </div>

                        {isDeepAnalysis && (
                          <div className="grid gap-4 md:grid-cols-3">
                            <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Factor Exposure</h4>
                              <div className="mt-3 space-y-2 text-xs">
                                <div className="flex justify-between gap-3"><span className="text-slate-400">Alpha</span><span className="font-mono text-slate-700">{formatNumber(factor.alpha_annualized)}</span></div>
                                <div className="flex justify-between gap-3"><span className="text-slate-400">Beta</span><span className="font-mono text-slate-700">{formatNumber(factor.market_beta)}</span></div>
                                <div className="flex justify-between gap-3"><span className="text-slate-400">Momentum</span><span className="font-mono text-slate-700">{formatNumber(factor.momentum_loading)}</span></div>
                                <div className="flex justify-between gap-3"><span className="text-slate-400">R-Squared</span><span className="font-mono text-slate-700">{formatNumber(factor.r_squared)}</span></div>
                              </div>
                            </div>
                            <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Options Market</h4>
                              <div className="mt-3 space-y-2 text-xs">
                                <div className="flex justify-between gap-3"><span className="text-slate-400">IV Rank</span><span className="font-mono text-slate-700">{formatNumber(options.iv_rank)}</span></div>
                                <div className="flex justify-between gap-3"><span className="text-slate-400">Put/Call</span><span className="font-mono text-slate-700">{formatNumber(options.put_call_ratio_volume)}</span></div>
                                <div className="flex justify-between gap-3"><span className="text-slate-400">Term Structure</span><span className="font-semibold text-slate-700">{options.term_structure || "NA"}</span></div>
                              </div>
                            </div>
                            <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Data Coverage</h4>
                              <div className="mt-3 space-y-2 text-xs">
                                <div className="flex justify-between gap-3"><span className="text-slate-400">Mode</span><span className="font-semibold uppercase text-slate-700">{sourceData.mode || "deep"}</span></div>
                                <div className="flex justify-between gap-3"><span className="text-slate-400">Fields</span><span className="font-mono text-slate-700">{quality.fields_received ?? "NA"} / {quality.fields_requested ?? "NA"}</span></div>
                                <div className="flex justify-between gap-3"><span className="text-slate-400">Quality</span><span className="font-mono text-slate-700">{formatNumber(quality.quality_score)}</span></div>
                              </div>
                            </div>
                          </div>
                        )}

                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                          {Object.entries(scores).map(([key, dim]: any) => {
                            const title = key.replace(/_/g, " ");
                            return (
                              <div key={key} className="rounded-lg border border-slate-200 bg-white/80 p-3 shadow-sm">
                                <h5 className="truncate text-[10px] font-bold uppercase tracking-wider text-slate-400" title={title}>{title}</h5>
                                <span className={`mt-2 inline-block rounded border px-2 py-0.5 text-[9px] font-extrabold uppercase ${getScoreBadgeClass(dim.score)}`}>
                                  {dim.score}
                                </span>
                                <p className="mt-2 text-[10px] leading-snug text-slate-500">{dim.rationale}</p>
                              </div>
                            );
                          })}
                        </div>

                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                            <h4 className="text-xs font-semibold text-slate-800 border-b border-slate-100 pb-2 mb-3">Peer & Moat Delta</h4>
                            <div className="space-y-2 text-xs text-slate-600">
                              <p>{peer.gross_margin_vs_peers}</p>
                              <p>{peer.current_ratio_vs_peers}</p>
                              <p className="font-semibold text-slate-500">Standing: {peer.overall_peer_standing || "in-line"}</p>
                            </div>
                          </div>
                          <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                            <h4 className="text-xs font-semibold text-slate-800 border-b border-slate-100 pb-2 mb-3">Smart Money Activity</h4>
                            <div className="space-y-2 text-xs text-slate-600">
                              <p>Insider: {smart.insider_signal}</p>
                              <p>Institutional: {smart.institutional_signal}</p>
                              <p>{smart.rationale}</p>
                            </div>
                          </div>
                        </div>

                        <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                          <h4 className="text-xs font-semibold text-slate-800 border-b border-slate-100 pb-2 mb-3">Risk Assessment</h4>
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <h5 className="text-[10px] font-bold uppercase tracking-wider text-rose-700 mb-2">Identified Flags</h5>
                              <ul className="space-y-1 text-xs text-slate-600">
                                {(risks.identified_risks || []).map((risk: string, idx: number) => <li key={idx}>{risk.replace(/_/g, " ")}</li>)}
                              </ul>
                            </div>
                            <div>
                              <h5 className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-2">Mitigating Strengths</h5>
                              <ul className="space-y-1 text-xs text-slate-600">
                                {(risks.mitigating_factors || []).map((fact: string, idx: number) => <li key={idx}>{fact}</li>)}
                              </ul>
                            </div>
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </div>
              )
            ) : (
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Overall holdings</div>
                  <div className="mt-2 font-mono text-2xl font-semibold text-slate-800">{portfolioOverview.total}</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Portfolio mix</div>
                  <div className="mt-2 text-sm font-semibold text-slate-800">{portfolioOverview.healthy} healthy, {portfolioOverview.neutral} neutral, {portfolioOverview.unhealthy} unhealthy</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Top sector</div>
                  <div className="mt-2 text-sm font-semibold text-slate-800">{portfolioOverview.topSector}</div>
                  <div className="mt-1 text-xs text-slate-400">{portfolioOverview.topSectorCount} holdings</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Combined latest price</div>
                  <div className="mt-2 font-mono text-2xl font-semibold text-slate-800">{formatCurrency(summary.investedValue)}</div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Average move</div>
                  <div className={`mt-2 font-mono text-2xl font-semibold ${portfolioOverview.avgChange >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                    {formatPercent(portfolioOverview.avgChange)}
                  </div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-white/80 p-4 shadow-sm">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Overall response</div>
                  <div className="mt-2 text-sm leading-relaxed text-slate-600">
                    Click a holding above to launch the model for that stock and populate the detailed response here.
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
