"use client";

import Link from "next/link";
import { ArrowLeft, Activity, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ProfileMenu } from "@/components/auth/ProfileMenu";
import { getPortfolioItems, PortfolioItem, removePortfolioItem } from "@/lib/portfolio";
import { formatCompact, formatCurrency, formatNumber, formatPercent } from "@/lib/formatters";
import type { Candle } from "@/lib/types";

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
    <div className="rounded border border-slate-200 p-3">
      <div className="text-xs font-medium uppercase text-slate-400">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold text-slate-800">{value}</div>
    </div>
  );
}

export function PortfolioClient() {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
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
    <main className="min-h-screen bg-slate-50 px-4 py-5 text-slate-700 md:px-8">
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
          <article className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="text-sm text-slate-400">Stocks added</div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-800">{items.length}</div>
          </article>
          <article className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="text-sm text-slate-400">Combined latest price</div>
            <div className="mt-2 font-mono text-2xl font-semibold text-slate-800">{formatCurrency(summary.investedValue)}</div>
          </article>
          <article className="rounded-lg border border-slate-200 bg-white p-4">
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
            <div className="rounded-lg border border-slate-200 bg-white">
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
            </div>

            <aside className="space-y-5">
              <section className="rounded-lg border border-slate-200 bg-white p-4">
                <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Stock Model <Activity className="h-4 w-4 text-slate-400" />
                </h2>
                <div className="grid grid-cols-2 gap-3">
                  <DetailMetric label="Company" value={selectedItem.name} />
                  <DetailMetric label="Sector" value={selectedItem.sector ?? "NA"} />
                  <DetailMetric label="Spot" value={formatCurrency(selectedItem.spot_price ?? selectedItem.price)} />
                  <DetailMetric label="Strike" value={formatNumber(selectedItem.strike_price)} />
                  <DetailMetric label="Risk-free" value={selectedItem.risk_free_rate === null ? "NA" : formatPercent(selectedItem.risk_free_rate * 100)} />
                  <DetailMetric label="Expiry" value={selectedItem.expiry_date ?? "NA"} />
                  <DetailMetric label="Revenue" value={selectedItem.revenue === null ? "Not in feed" : formatCompact(selectedItem.revenue)} />
                  <DetailMetric label="Health" value={selectedItem.health_status ?? selectedItem.config?.healthStatus ?? "Neutral"} />
                </div>
                <p className="mt-4 rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm leading-6 text-slate-500">
                  {selectedItem.health_reason ?? selectedItem.config?.healthReason ?? "Health is derived from the available price history."}
                </p>
              </section>
            </aside>
          </section>
        )}

        <section className="rounded-lg border border-slate-200 bg-white">
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
                <thead className="bg-slate-50 text-xs uppercase text-slate-400">
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
