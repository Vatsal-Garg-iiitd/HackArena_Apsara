import type { Company, MarketIndex } from "@/lib/types";
import type { PortfolioConfig } from "@/lib/portfolio-model";
import { buildPortfolioConfig } from "@/lib/portfolio-model";
import { supabase } from "@/lib/supabase";

export type PortfolioItem = {
  id: string;
  user_id: string;
  symbol: string;
  ticker: string | null;
  name: string;
  sector: string | null;
  index_key: MarketIndex["key"] | null;
  index_name: string | null;
  market_cap: number | null;
  price: number | null;
  change: number | null;
  change_percent: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  previous_close: number | null;
  volume: number | null;
  spot_price: number | null;
  strike_price: number | null;
  risk_free_rate: number | null;
  expiry_date: string | null;
  revenue: number | null;
  health_status: PortfolioConfig["healthStatus"] | null;
  health_reason: string | null;
  source_reference: string | null;
  stock_snapshot: Company;
  config: PortfolioConfig;
  created_at: string;
  updated_at: string;
};

function schemaMessage(message: string) {
  if (message.includes("portfolio_items") || message.toLowerCase().includes("schema cache")) {
    return "Portfolio table is missing in Supabase. Run supabase/profiles.sql or supabase/models/portfolio_items.sql in the Supabase SQL editor.";
  }

  return message;
}

export async function getPortfolioItems() {
  if (!supabase) return { items: [] as PortfolioItem[], error: "Supabase is not configured." };

  const { data, error } = await supabase
    .from("portfolio_items")
    .select("*")
    .order("created_at", { ascending: false });

  return { items: (data ?? []) as PortfolioItem[], error: error?.message ? schemaMessage(error.message) : null };
}

export async function addCompanyToPortfolio(company: Company, index: MarketIndex) {
  if (!supabase) return { error: "Supabase is not configured." };

  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) {
    return { error: "Please login before adding stocks to your portfolio." };
  }

  const config = buildPortfolioConfig(company, index);

  const { error } = await supabase.from("portfolio_items").upsert(
    {
      user_id: userData.user.id,
      symbol: company.symbol,
      ticker: company.ticker,
      name: company.name,
      sector: company.sector,
      index_key: index.key,
      index_name: index.name,
      market_cap: company.marketCap,
      price: company.price,
      change: company.change,
      change_percent: company.changePercent,
      open: company.open,
      high: company.high,
      low: company.low,
      previous_close: company.previousClose,
      volume: company.volume,
      spot_price: config.spotPrice,
      strike_price: config.strikePrice,
      risk_free_rate: config.riskFreeRate,
      expiry_date: config.expiryDate,
      revenue: config.revenue,
      health_status: config.healthStatus,
      health_reason: config.healthReason,
      source_reference: config.sourceReference,
      stock_snapshot: company,
      config,
      updated_at: new Date().toISOString()
    },
    { onConflict: "user_id,symbol" }
  );

  return { error: error?.message ? schemaMessage(error.message) : null };
}

export async function removePortfolioItem(symbol: string) {
  if (!supabase) return { error: "Supabase is not configured." };

  const { error } = await supabase.from("portfolio_items").delete().eq("symbol", symbol);
  return { error: error?.message ? schemaMessage(error.message) : null };
}
