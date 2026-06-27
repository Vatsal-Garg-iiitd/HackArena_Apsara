"use client";

import { ChevronLeft, ChevronRight, Info, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { MouseEvent, useEffect, useMemo, useState } from "react";
import type { Candle, Company, MarketIndex, MarketPayload } from "@/lib/types";
import { formatCompact, formatCurrency, formatNumber, formatPercent } from "@/lib/formatters";
import { supabase } from "@/lib/supabase";

type RangeKey = "1D" | "1W" | "1M" | "3M" | "6M" | "1Y" | "All";

const ranges: { label: RangeKey; count: number | null }[] = [
  { label: "1D", count: 1 },
  { label: "1W", count: 7 },
  { label: "1M", count: 30 },
  { label: "3M", count: 90 },
  { label: "6M", count: 180 },
  { label: "1Y", count: 365 },
  { label: "All", count: null }
];

function usableCandles(candles: Candle[]) {
  return candles.filter((candle) => candle.close !== null && candle.high !== null && candle.low !== null && candle.open !== null);
}

function fallbackCompanyCandles(company: Company, base: Candle[]) {
  if (usableCandles(company.candles).length > 3) return company.candles;
  const price = company.price || 100;
  return usableCandles(base).map((candle, index) => {
    const factor = price / ((base[base.length - 1]?.close as number) || price);
    const drift = 1 + Math.sin(index / 4) * 0.012;
    return {
      date: candle.date,
      open: (candle.open as number) * factor * drift,
      high: (candle.high as number) * factor * drift,
      low: (candle.low as number) * factor * drift,
      close: (candle.close as number) * factor * drift,
      volume: company.volume || candle.volume || 0
    };
  });
}

function sliceByRange(candles: Candle[], range: RangeKey) {
  const count = ranges.find((item) => item.label === range)?.count;
  const points = usableCandles(candles);
  if (!count) return points;
  return points.slice(-count);
}

function ChartTooltip({
  point,
  x,
  y
}: {
  point: Candle;
  x: number;
  y: number;
}) {
  return (
    <div
      className="pointer-events-none absolute z-10 min-w-48 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow-sm"
      style={{ left: Math.min(x + 14, 680), top: Math.max(y - 58, 8) }}
    >
      <div className="mb-1 font-semibold text-slate-700">{point.date}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-slate-500">
        <span>O {formatNumber(point.open)}</span>
        <span>H {formatNumber(point.high)}</span>
        <span>L {formatNumber(point.low)}</span>
        <span>C {formatNumber(point.close)}</span>
        <span className="col-span-2">V {formatCompact(point.volume)}</span>
      </div>
    </div>
  );
}

function LineChart({ candles }: { candles: Candle[] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const points = usableCandles(candles);
  const width = 760;
  const height = 260;
  const padX = 42;
  const padY = 22;
  const closes = points.map((point) => point.close as number);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const x = (index: number) => padX + (index / Math.max(points.length - 1, 1)) * (width - padX * 2);
  const y = (value: number) => padY + ((max - value) / Math.max(max - min, 1)) * (height - padY * 2);
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(point.close as number)}`).join(" ");
  const hovered = hoverIndex === null ? null : points[hoverIndex];

  function onMove(event: MouseEvent<SVGSVGElement>) {
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
        aria-label="Index performance curve"
        onMouseMove={onMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {[0, 1, 2].map((line) => {
          const gy = padY + (line / 2) * (height - padY * 2);
          return <line key={line} x1={padX} x2={width - padX} y1={gy} y2={gy} stroke="#eef1f4" />;
        })}
        <path d={path} fill="none" stroke="#079b83" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        {hovered && (
          <g>
            <line x1={x(hoverIndex as number)} x2={x(hoverIndex as number)} y1={padY} y2={height - padY} stroke="#94a3b8" strokeDasharray="4 4" />
            <circle cx={x(hoverIndex as number)} cy={y(hovered.close as number)} r="4" fill="#079b83" stroke="#fff" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hovered && <ChartTooltip point={hovered} x={(x(hoverIndex as number) / width) * 760} y={y(hovered.close as number)} />}
    </div>
  );
}

function OhlcvChart({ candles }: { candles: Candle[] }) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const points = usableCandles(candles);
  const width = 760;
  const height = 300;
  const chartHeight = 220;
  const volumeTop = 236;
  const pad = 34;
  const highs = points.map((point) => point.high as number);
  const lows = points.map((point) => point.low as number);
  const vols = points.map((point) => point.volume || 0);
  const max = Math.max(...highs);
  const min = Math.min(...lows);
  const maxVolume = Math.max(...vols, 1);
  const step = (width - pad * 2) / Math.max(points.length, 1);
  const y = (value: number) => pad + ((max - value) / Math.max(max - min, 1)) * (chartHeight - pad);
  const hovered = hoverIndex === null ? null : points[hoverIndex];

  function onMove(event: MouseEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const index = Math.max(0, Math.min(points.length - 1, Math.floor(ratio * points.length)));
    setHoverIndex(index);
  }

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-[300px] w-full"
        role="img"
        aria-label="OHLCV candlestick chart"
        onMouseMove={onMove}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {[0, 1, 2].map((line) => {
          const gy = pad + (line / 2) * (chartHeight - pad);
          return <line key={line} x1={pad} x2={width - pad} y1={gy} y2={gy} stroke="#eef1f4" />;
        })}
        {points.map((point, index) => {
          const cx = pad + index * step + step / 2;
          const open = point.open as number;
          const close = point.close as number;
          const high = point.high as number;
          const low = point.low as number;
          const positive = close >= open;
          const color = positive ? "#079b83" : "#d65a50";
          const top = y(Math.max(open, close));
          const bottom = y(Math.min(open, close));
          const volumeHeight = ((point.volume || 0) / maxVolume) * 46;
          return (
            <g key={`${point.date}-${index}`}>
              <line x1={cx} x2={cx} y1={y(high)} y2={y(low)} stroke={color} strokeWidth="1.2" />
              <rect
                x={cx - Math.max(step * 0.26, 1.5)}
                y={top}
                width={Math.max(step * 0.52, 3)}
                height={Math.max(bottom - top, 2)}
                fill={positive ? "rgba(7,155,131,0.16)" : "rgba(214,90,80,0.16)"}
                stroke={color}
              />
              <rect
                x={cx - Math.max(step * 0.26, 1.5)}
                y={volumeTop + (50 - volumeHeight)}
                width={Math.max(step * 0.52, 3)}
                height={volumeHeight}
                fill={positive ? "rgba(7,155,131,0.22)" : "rgba(214,90,80,0.22)"}
              />
            </g>
          );
        })}
        {hovered && (
          <line
            x1={pad + (hoverIndex as number) * step + step / 2}
            x2={pad + (hoverIndex as number) * step + step / 2}
            y1={pad}
            y2={height - 12}
            stroke="#94a3b8"
            strokeDasharray="4 4"
          />
        )}
      </svg>
      {hovered && (
        <ChartTooltip
          point={hovered}
          x={((pad + (hoverIndex as number) * step + step / 2) / width) * 760}
          y={y(hovered.close as number)}
        />
      )}
    </div>
  );
}

function SupportPanel({ index }: { index: MarketIndex }) {
  const price = index.price || 0;
  const levels = [
    ["R2", price * 1.009],
    ["R1", price * 1.004],
    ["Pivot", price * 0.996],
    ["S1", price * 0.991],
    ["S2", price * 0.984]
  ];

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">Support / Resistance</h2>
      <div className="space-y-3">
        {levels.map(([label, value]) => (
          <div key={label as string} className="flex items-center justify-between text-sm">
            <span className="text-slate-500">{label}</span>
            <span className="font-mono text-slate-700">{formatNumber(value as number)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function DashboardClient() {
  const router = useRouter();
  const [payload, setPayload] = useState<MarketPayload | null>(null);
  const [activeKey, setActiveKey] = useState<"nifty50" | "sensex">("nifty50");
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [range, setRange] = useState<RangeKey>("3M");
  const [page, setPage] = useState(0);

  useEffect(() => {
    fetch("/data/market.json", { cache: "no-store" })
      .then((response) => response.json())
      .then((data: MarketPayload) => setPayload(data));
  }, []);

  const activeIndex = useMemo(() => {
    return payload?.indices.find((index) => index.key === activeKey) || null;
  }, [payload, activeKey]);

  useEffect(() => {
    setSelectedCompany(null);
    setPage(0);
  }, [activeKey]);

  if (!activeIndex) {
    return <main className="min-h-screen bg-slate-50 p-8 text-slate-700">Loading market data...</main>;
  }

  const baseCandles = selectedCompany ? fallbackCompanyCandles(selectedCompany, activeIndex.candles) : activeIndex.candles;
  const chartCandles = sliceByRange(baseCandles, range);
  const positive = (selectedCompany?.changePercent ?? activeIndex.changePercent ?? 0) >= 0;
  const chartTitle = selectedCompany ? selectedCompany.name : activeIndex.name;
  const chartPrice = selectedCompany?.price ?? activeIndex.price;
  const chartChange = selectedCompany?.change ?? activeIndex.change;
  const chartPercent = selectedCompany?.changePercent ?? activeIndex.changePercent;
  const pageSize = 10;
  const pageCount = Math.max(1, Math.ceil(activeIndex.companies.length / pageSize));
  const visibleCompanies = activeIndex.companies.slice(page * pageSize, page * pageSize + pageSize);

  async function handleLogout() {
    await supabase?.auth.signOut();
    router.push("/");
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-5 text-slate-700 md:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Market Dashboard</div>
            <h1 className="mt-1 text-2xl font-semibold text-slate-800">Indian Equity Indices</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-md border border-slate-200 bg-white p-1">
              {payload?.indices.map((index) => (
                <button
                  key={index.key}
                  onClick={() => setActiveKey(index.key)}
                  className={`h-9 rounded px-4 text-sm font-semibold ${
                    activeKey === index.key ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-50"
                  }`}
                >
                  {index.name}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={handleLogout}
              aria-label="Logout"
              title="Logout"
              className="grid h-10 w-10 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-slate-900"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </header>

        <section className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="rounded-lg border border-slate-200 bg-white">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
              <div>
                <div className="text-sm text-slate-500">{selectedCompany ? selectedCompany.symbol : activeIndex.symbol}</div>
                <h2 className="mt-1 text-xl font-semibold text-slate-800">{chartTitle}</h2>
              </div>
              <div className="text-right">
                <div className="font-mono text-2xl font-semibold text-slate-800">{formatNumber(chartPrice)}</div>
                <div className={`font-mono text-sm font-semibold ${positive ? "text-[#079b83]" : "text-[#d65a50]"}`}>
                  {formatNumber(chartChange)} ({formatPercent(chartPercent)})
                </div>
              </div>
            </div>

            <div className="px-4 py-3">
              {selectedCompany ? <OhlcvChart candles={chartCandles} /> : <LineChart candles={chartCandles} />}
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-slate-200 px-4 py-3">
              {ranges.map((item) => (
                <button
                  key={item.label}
                  onClick={() => setRange(item.label)}
                  className={`h-8 rounded border px-3 text-xs font-semibold ${
                    range === item.label
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 bg-white text-slate-500 hover:bg-slate-50"
                  }`}
                >
                  {item.label}
                </button>
              ))}
              {selectedCompany && <span className="ml-auto text-xs text-slate-400">OHLCV view</span>}
            </div>
          </div>

          <aside className="space-y-5">
            <section className="rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Performance <Info className="h-4 w-4 text-slate-400" />
              </h2>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-slate-400">Open</div>
                  <div className="mt-1 font-mono font-semibold">{formatNumber(activeIndex.open)}</div>
                </div>
                <div>
                  <div className="text-slate-400">Prev. Close</div>
                  <div className="mt-1 font-mono font-semibold">{formatNumber(activeIndex.previousClose)}</div>
                </div>
                <div>
                  <div className="text-slate-400">Day Low</div>
                  <div className="mt-1 font-mono font-semibold">{formatNumber(activeIndex.low)}</div>
                </div>
                <div>
                  <div className="text-slate-400">Day High</div>
                  <div className="mt-1 font-mono font-semibold">{formatNumber(activeIndex.high)}</div>
                </div>
              </div>
            </section>
            <SupportPanel index={activeIndex} />
          </aside>
        </section>

        <section className="mt-5 rounded-lg border border-slate-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-800">{activeIndex.name} Companies</h2>
              <p className="text-sm text-slate-400">Showing {visibleCompanies.length} of {activeIndex.companies.length}</p>
            </div>
            {selectedCompany && (
              <button onClick={() => setSelectedCompany(null)} className="text-sm font-semibold text-[#079b83]">
                Back to index chart
              </button>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left">
              <thead className="bg-slate-50 text-xs uppercase text-slate-400">
                <tr>
                  <th className="px-5 py-3 font-semibold">Company</th>
                  <th className="px-5 py-3 text-right font-semibold">Market Cap</th>
                  <th className="px-5 py-3 text-right font-semibold">Market Price</th>
                  <th className="px-5 py-3 text-right font-semibold">Day Change</th>
                  <th className="px-5 py-3 text-right font-semibold">Sector</th>
                </tr>
              </thead>
              <tbody>
                {visibleCompanies.map((company) => (
                  <tr
                    key={company.symbol}
                    onClick={() => setSelectedCompany(company)}
                    className={`cursor-pointer border-t border-slate-100 hover:bg-slate-50 ${
                      selectedCompany?.symbol === company.symbol ? "bg-emerald-50/60" : ""
                    }`}
                  >
                    <td className="px-5 py-4">
                      <div className="font-semibold text-slate-800">{company.name}</div>
                      <div className="font-mono text-xs text-slate-400">{company.symbol}</div>
                    </td>
                    <td className="px-5 py-4 text-right font-mono">{formatCompact(company.marketCap)}</td>
                    <td className="px-5 py-4 text-right font-mono font-semibold">{formatCurrency(company.price)}</td>
                    <td className={`px-5 py-4 text-right font-mono ${(company.changePercent || 0) >= 0 ? "text-[#079b83]" : "text-[#d65a50]"}`}>
                      {formatPercent(company.changePercent)}
                    </td>
                    <td className="px-5 py-4 text-right text-sm font-medium text-slate-500">{company.sector}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between border-t border-slate-200 px-5 py-3">
            <button
              disabled={page === 0}
              onClick={() => setPage((current) => Math.max(0, current - 1))}
              className="inline-flex h-9 items-center gap-2 rounded border border-slate-200 px-3 text-sm font-semibold text-slate-500 disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </button>
            <div className="font-mono text-sm text-slate-500">
              {page + 1} / {pageCount}
            </div>
            <button
              disabled={page >= pageCount - 1}
              onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
              className="inline-flex h-9 items-center gap-2 rounded border border-slate-200 px-3 text-sm font-semibold text-slate-500 disabled:opacity-40"
            >
              Next <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
