import type { Candle, Company, MarketIndex } from "@/lib/types";

export type PortfolioConfig = {
  source: "dashboard";
  sourceReference: "yahoo_fin.stock_info";
  addedFrom: MarketIndex["key"];
  watchMode: "manual";
  spotPrice: number | null;
  strikePrice: number | null;
  riskFreeRate: number;
  expiryDate: string;
  revenue: number | null;
  healthStatus: "Healthy" | "Unhealthy" | "Neutral";
  healthReason: string;
};

function validCloses(candles: Candle[]) {
  return candles
    .map((candle) => candle.close)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

export function getNextMonthlyExpiry(from = new Date()) {
  const year = from.getFullYear();
  const month = from.getMonth();
  const lastDay = new Date(year, month + 1, 0);

  while (lastDay.getDay() !== 4) {
    lastDay.setDate(lastDay.getDate() - 1);
  }

  if (lastDay <= from) {
    return getNextMonthlyExpiry(new Date(year, month + 1, 1));
  }

  return lastDay.toISOString().slice(0, 10);
}

export function deriveStrikePrice(price: number | null) {
  if (!price) return null;
  const step = price >= 1000 ? 50 : 10;
  return Math.round(price / step) * step;
}

export function deriveHealth(candles: Candle[]) {
  const closes = validCloses(candles);
  if (closes.length < 2) {
    return {
      healthStatus: "Neutral" as const,
      healthReason: "Not enough historical candle data is available."
    };
  }

  const first = closes[0];
  const last = closes[closes.length - 1];
  const changePercent = ((last - first) / first) * 100;

  if (changePercent > 1) {
    return {
      healthStatus: "Healthy" as const,
      healthReason: "Historical close price is rising over the available period."
    };
  }

  if (changePercent < -1) {
    return {
      healthStatus: "Unhealthy" as const,
      healthReason: "Historical close price is decreasing over the available period."
    };
  }

  return {
    healthStatus: "Neutral" as const,
    healthReason: "Historical close price is broadly flat over the available period."
  };
}

export function buildPortfolioConfig(company: Company, index: MarketIndex): PortfolioConfig {
  const health = deriveHealth(company.candles);

  return {
    source: "dashboard",
    sourceReference: "yahoo_fin.stock_info",
    addedFrom: index.key,
    watchMode: "manual",
    spotPrice: company.price,
    strikePrice: deriveStrikePrice(company.price),
    riskFreeRate: 0.065,
    expiryDate: getNextMonthlyExpiry(),
    revenue: null,
    ...health
  };
}
