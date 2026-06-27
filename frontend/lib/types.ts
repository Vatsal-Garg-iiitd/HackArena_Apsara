export type Candle = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type Company = {
  symbol: string;
  ticker: string;
  name: string;
  sector: string;
  marketCap: number | null;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  previousClose: number | null;
  volume: number | null;
  candles: Candle[];
};

export type MarketIndex = {
  key: "nifty50" | "sensex";
  name: string;
  symbol: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  previousClose: number | null;
  volume: number | null;
  candles: Candle[];
  companies: Company[];
};

export type MarketPayload = {
  generatedAt: string;
  source: string;
  indices: MarketIndex[];
};
