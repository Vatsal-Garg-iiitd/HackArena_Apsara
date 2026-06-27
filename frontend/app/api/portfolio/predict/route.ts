import { NextRequest, NextResponse } from "next/server";
import { deriveAnnualVolatility, OptionType, predictHorizons } from "@/lib/option-pricing";
import type { Company } from "@/lib/types";

type PredictRequest = {
  symbol: string;
  name: string;
  price: number | null;
  strike_price?: number | null;
  risk_free_rate?: number | null;
  option_type?: OptionType;
  num_paths?: number | null;
  stock_snapshot?: Company | null;
};

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as PredictRequest;
    const snapshot = body.stock_snapshot;
    const S = body.price ?? snapshot?.price ?? null;

    if (!body.symbol || !snapshot) {
      return NextResponse.json({ error: "A saved portfolio stock snapshot is required." }, { status: 400 });
    }

    if (!S || S <= 0) {
      return NextResponse.json({ error: "Current stock price is missing for this portfolio item." }, { status: 400 });
    }

    const sigma = deriveAnnualVolatility(snapshot.candles ?? []);
    if (!sigma) {
      return NextResponse.json({ error: "Not enough historical Yahoo data to derive volatility." }, { status: 400 });
    }

    const K = body.strike_price && body.strike_price > 0 ? body.strike_price : S;
    const r = body.risk_free_rate ?? 0.05;
    const num_paths = Math.max(100, Math.min(body.num_paths ?? 10000, 100000));
    const option_type = body.option_type ?? "call";

    const predictions = predictHorizons({
      S,
      K,
      r,
      sigma,
      option_type,
      num_paths
    });

    return NextResponse.json({
      ticker: body.symbol,
      company_name: body.name,
      data_source: "yahoo_fin.stock_info snapshot",
      derived_parameters: {
        S,
        K,
        r,
        sigma,
        option_type,
        num_paths,
        lookback_days: Math.min(snapshot.candles?.length ?? 0, 252)
      },
      predictions
    });
  } catch {
    return NextResponse.json({ error: "Unable to calculate portfolio predictions." }, { status: 500 });
  }
}
