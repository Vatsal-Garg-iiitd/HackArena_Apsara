"use client";

import Link from "next/link";
import { ArrowLeft, Activity, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ProfileMenu } from "@/components/auth/ProfileMenu";
import { getPortfolioItems, PortfolioItem, removePortfolioItem } from "@/lib/portfolio";
import { formatCompact, formatCurrency, formatNumber, formatPercent } from "@/lib/formatters";
import type { Candle } from "@/lib/types";

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

function usableCandles(candles: Candle[]) {
  return candles.filter((candle) => candle.close !== null && candle.high !== null && candle.low !== null && candle.open !== null);
}

function PortfolioChart({ candles }: { candles: Candle[] }) {
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

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-[260px] w-full" role="img" aria-label="Portfolio stock price history">
      {[0, 1, 2].map((line) => {
        const gy = padY + (line / 2) * (height - padY * 2);
        return <line key={line} x1={padX} x2={width - padX} y1={gy} y2={gy} stroke="#eef1f4" />;
      })}
      <path d={path} fill="none" stroke={stroke} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d={`${path} L ${width - padX} ${height - padY} L ${padX} ${height - padY} Z`} fill={rising ? "rgba(7,155,131,0.08)" : "rgba(214,90,80,0.08)"} />
    </svg>
  );
}

function DetailMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-200 bg-white/80 p-3 shadow-sm">
      <div className="text-xs font-medium uppercase text-slate-400">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold text-slate-800">{value}</div>
    </div>
  );
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

  useEffect(() => {
    getPortfolioItems().then(({ items: portfolioItems, error }) => {
      setItems(portfolioItems);
      setSelectedSymbol(portfolioItems[0]?.symbol ?? null);
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
    return items.find((item) => item.symbol === selectedSymbol) ?? items[0] ?? null;
  }, [items, selectedSymbol]);

  useEffect(() => {
    if (!selectedItem) {
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
        symbol: selectedItem.symbol,
        name: selectedItem.name,
        price: selectedItem.spot_price ?? selectedItem.price,
        strike_price: selectedItem.strike_price,
        risk_free_rate: selectedItem.risk_free_rate,
        option_type: "call",
        num_paths: 10000,
        stock_snapshot: selectedItem.stock_snapshot
      })
    })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Prediction failed.");
        return data as PortfolioPrediction;
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
  }, [selectedItem]);

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
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Sentiment fetch failed.");
        return data as StockSentiment;
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
      if (selectedSymbol === symbol) setSelectedSymbol(next[0]?.symbol ?? null);
      return next;
    });
    setMessage(`${symbol} removed from portfolio.`);
  }

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

        {selectedItem && (
          <section className="mb-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="surface-panel rounded-lg border">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
                <div>
                  <div className="font-mono text-sm text-slate-500">{selectedItem.symbol}</div>
                  <h2 className="mt-1 text-xl font-semibold text-slate-800">{selectedItem.name}</h2>
                  <p className="mt-1 text-sm text-slate-400">{selectedItem.sector} · {selectedItem.index_name}</p>
                </div>
                <div className="text-right">
                  <div className="font-mono text-2xl font-semibold text-slate-800">{formatCurrency(selectedItem.spot_price ?? selectedItem.price)}</div>
                  <div className={`font-mono text-sm font-semibold ${(selectedItem.change_percent ?? 0) >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                    {formatNumber(selectedItem.change)} ({formatPercent(selectedItem.change_percent)})
                  </div>
                </div>
              </div>
              <div className="px-4 py-3">
                <PortfolioChart candles={selectedItem.stock_snapshot?.candles ?? []} />
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
                    {prediction.predictions.map((row) => (
                      <div key={row.horizon_days} className="rounded border border-slate-200 bg-white/85 p-3 shadow-sm">
                        <div className="mb-3 flex items-center justify-between">
                          <span className="text-sm font-semibold text-slate-700">Day {row.horizon_days}</span>
                          <span className="font-mono text-lg font-semibold text-emerald-700">
                            {formatCurrency(row.average_price)}
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs text-slate-600">
                          <span className="rounded bg-slate-50 px-2 py-1">MC {formatCurrency(row.methods.monte_carlo.price)}</span>
                          <span className="rounded bg-slate-50 px-2 py-1">FOSM {formatCurrency(row.methods.fosm.price)}</span>
                          <span className="rounded bg-slate-50 px-2 py-1">PEM {formatCurrency(row.methods.pem.price)}</span>
                          <span className="rounded bg-slate-50 px-2 py-1">Taguchi {formatCurrency(row.methods.taguchi.price)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded border border-slate-200 bg-white/80 px-3 py-4 text-sm text-slate-500">
                    Select a portfolio stock to calculate predictions.
                  </div>
                )}
              </div>
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
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">Stock Snapshot</h2>
                <div className="grid grid-cols-2 gap-3">
                  <DetailMetric label="Spot" value={formatCurrency(selectedItem.spot_price ?? selectedItem.price)} />
                  <DetailMetric label="Strike" value={formatNumber(selectedItem.strike_price)} />
                  <DetailMetric label="Risk-free" value={selectedItem.risk_free_rate === null ? "NA" : formatPercent(selectedItem.risk_free_rate * 100)} />
                  <DetailMetric label="Health" value={selectedItem.health_status ?? selectedItem.config?.healthStatus ?? "Neutral"} />
                </div>
              </section>
            </aside>
          </section>
        )}

        <section className="surface-panel rounded-lg border">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-lg font-semibold text-slate-800">Portfolio holdings</h2>
            <p className="text-sm text-slate-400">Saved per user in Supabase for future computation and calculations.</p>
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
      </div>
    </main>
  );
}
