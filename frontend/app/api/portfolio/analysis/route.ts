import { NextRequest, NextResponse } from "next/server";

const PIPELINE_API_URL = process.env.PIPELINE_API_URL || "http://127.0.0.1:8765";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { symbol, force_refresh = false } = body;
    const requestedMode = body.mode === "deep" ? "deep" : "standard";

    if (!symbol) {
      return NextResponse.json({ error: "Stock symbol is required." }, { status: 400 });
    }

    const cleanSymbol = symbol.trim().toUpperCase();

    try {
      // 1. Run the advanced pipeline for the ticker
      const pipelineRes = await fetch(`${PIPELINE_API_URL}/v1/pipeline/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tickers: [cleanSymbol],
          force_refresh,
          mode: "fast"
        }),
        signal: AbortSignal.timeout(45000) // 45 seconds timeout
      });

      if (!pipelineRes.ok) {
        throw new Error(`Pipeline API returned HTTP ${pipelineRes.status}`);
      }

      const pipelineData = await pipelineRes.json();
      const pipelineResult = pipelineData.results?.[cleanSymbol] || null;

      // 2. Fetch the fundamental analysis report
      const fundamentalsRes = await fetch(
        `${PIPELINE_API_URL}/v1/fundamentals/${cleanSymbol}?mode=${requestedMode}`,
        {
          method: "GET",
          signal: AbortSignal.timeout(15000)
        }
      );

      let fundamentalsResult = null;
      if (fundamentalsRes.ok) {
        fundamentalsResult = await fundamentalsRes.json();
      }

      return NextResponse.json({
        symbol: cleanSymbol,
        mode: requestedMode,
        fallback: false,
        pipeline: pipelineResult,
        fundamentals: fundamentalsResult
      });

    } catch (apiError) {
      console.warn("FastAPI backend is offline or failed. Falling back to mock data.", apiError);

      // Return high-quality mock data when backend is down
      const mockData = generateMockAnalysis(cleanSymbol, requestedMode);
      return NextResponse.json({
        symbol: cleanSymbol,
        mode: requestedMode,
        fallback: true,
        pipeline: mockData.pipeline,
        fundamentals: mockData.fundamentals
      });
    }

  } catch (error: any) {
    return NextResponse.json(
      { error: error?.message || "Failed to process analysis request." },
      { status: 500 }
    );
  }
}

function generateMockAnalysis(symbol: string, mode: "standard" | "deep" = "standard") {
  const isIndian = symbol.endsWith(".NS") || symbol.endsWith(".BO");
  const cleanSymbol = symbol.replace(/\.(NS|BO)$/i, "");
  
  // Custom mock values based on ticker for predictability
  const hash = cleanSymbol.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  
  const tacticalDir = hash % 3 === 0 ? "bullish" : hash % 3 === 1 ? "bearish" : "neutral";
  const structuralDir = hash % 2 === 0 ? "bullish" : "neutral";
  
  const solvencyScore = hash % 5 === 0 ? "weak" : hash % 5 === 4 ? "moderate" : "strong";
  const profitScore = hash % 3 === 0 ? "strong" : "stable";
  
  return {
    pipeline: {
      ticker: symbol,
      signals: {
        tactical_horizon_30d: {
          direction: tacticalDir,
          confidence: 0.65 + (hash % 30) / 100,
          corroborating_signals: [
            `MACD histogram showing ${tacticalDir === "bullish" ? "upward momentum shift" : "downward slope contraction"}`,
            `RSI is moderate at ${45 + (hash % 20)}, indicating room for extension`,
            "Price successfully testing major support near 20-day moving average"
          ],
          contradicting_signals: [
            "Volume profile is slightly thin on break-out bars",
            "Short-term ATR indicates rising volatility spikes"
          ],
          data_quality_score: 0.95
        },
        structural_horizon_1y: {
          direction: structuralDir,
          confidence: 0.75 + (hash % 20) / 100,
          corroborating_signals: [
            `Robust net interest margin stack compared to industry medians`,
            `Solid quick ratio of ${1.2 + (hash % 10)/10}x providing significant buffer`,
            "Strong competitive moat driven by high customer retention rates"
          ],
          contradicting_signals: [
            "CapEx guidance for the next fiscal year expanded by 15%",
            isIndian ? "Exchange rate headwinds affecting overseas revenues" : "Regulatory scrutiny in European operations"
          ],
          data_quality_score: 1.0
        }
      },
      overall_confidence: 0.72,
      rationale: `The General Expert sees a divergence between short-term momentum and structural strength. While ${cleanSymbol} stands strong on core liquidity metrics, tactical positioning is currently ${tacticalDir} with moderate confidence. We recommend aligning exposure to long-term value points rather than trying to capture near-term volatility spikes.`,
      conflicting_signals: [
        "Short-term technical consolidation contrasts with upward revisions in forward earnings expectations.",
        "Insider trading is neutral while institutional flow indicates moderate accumulation."
      ],
      data_quality_score: 0.95,
      macro_regime_adjustment: "Bearish macro adjustment applied: 15% confidence penalty to bullish tactical moves due to rising rate environment.",
      consistency_flags: []
    },
    fundamentals: {
      ticker: symbol,
      analysis_date: new Date().toISOString().split("T")[0],
      executive_summary: `${cleanSymbol} demonstrates a ${profitScore} profitability profile coupled with a ${solvencyScore} balance sheet. Working capital buffers are sufficient for operations, though peer medians indicate competitive pressure on pricing power.`,
      dimension_scores: {
        revenue_quality: {
          score: profitScore,
          rationale: "Revenue growth has been consistent at 8-12% YoY, supported by steady recurring contract wins."
        },
        balance_sheet_health: {
          score: solvencyScore,
          rationale: `Solvency metrics show a debt-to-equity ratio of ${1.4 + (hash % 10)/10} and current ratio of ${1.1 + (hash % 10)/10}.`
        },
        cash_flow_quality: {
          score: hash % 2 === 0 ? "strong" : "moderate",
          rationale: "Operating cash flow conversion matches accounting earnings with high reliability."
        },
        competitive_position: {
          score: "strong",
          rationale: "Peer-normalized margins remain positive, suggesting stable competitive positioning."
        },
        valuation_attractiveness: {
          score: hash % 3 === 0 ? "attractive" : "fair",
          rationale: "P/E multiple is trading near the 5-year historical average, suggesting reasonable pricing."
        }
      },
      peer_comparison: {
        gross_margin_vs_peers: `Gross margin is ${2.5 + (hash % 5)}% above the industry peer median.`,
        current_ratio_vs_peers: `Current ratio is ${hash % 2 === 0 ? "0.15 above" : "0.08 below"} the industry peer median.`,
        overall_peer_standing: hash % 3 === 0 ? "leader" : "in-line"
      },
      smart_money_read: {
        insider_signal: hash % 3 === 0 ? "bullish" : "neutral",
        institutional_signal: "accumulating",
        rationale: "Insiders recorded net buys over the last 90 days, while institutional holdings remain stable."
      },
      risk_assessment: {
        identified_risks: [
          solvencyScore === "weak" ? "higher_debt_leverage" : "margin_compression_from_input_costs",
          "dependence_on_key_geographic_regions",
          "cybersecurity_compliance_overheads"
        ],
        severity: solvencyScore === "weak" ? "high" : "medium",
        mitigating_factors: [
          "Healthy interest coverage ratio above 4.5x",
          "Contractual inflation pass-through clauses"
        ]
      },
      forward_outlook: {
        eps_revision_commentary: "Wall Street consensus has revised EPS estimates up by 2% for the coming quarter.",
        guidance_commentary: "Management expects double-digit growth in digital segments with stable margins.",
        analyst_consensus_commentary: "Out of 18 analysts, 12 maintain a BUY rating, 5 HOLD, and 1 SELL."
      },
      macro_fit: {
        regime: "neutral_macro",
        impact_on_this_stock: "Stable rates provide a neutral backdrop, making company-specific performance the primary driver."
      },
      conflicting_signals: [
        "Short-term price consolidation contrasts with upward revisions in forward earnings expectations."
      ],
      final_signals: {
        tactical_30d: {
          signal: tacticalDir === "bullish" ? "buy" : tacticalDir === "bearish" ? "sell" : "hold",
          confidence: "medium",
          rationale: `Driven by short-term MACD cross and RSI level of ${50 + (hash % 10)}.`
        },
        structural_1y: {
          signal: structuralDir === "bullish" ? "buy" : "hold",
          confidence: "high",
          rationale: "Long-term investment case is underpinned by high return on capital and defensive market position."
        }
      },
      one_line_verdict: `${cleanSymbol} is a ${structuralDir === "bullish" ? "BUY" : "HOLD"} on long-term quality, with tactical support rated ${tacticalDir.toUpperCase()}.`,
      source_data: {
        mode,
        factor_exposure: {
          alpha_annualized: ((hash % 12) - 4) / 100,
          market_beta: 0.8 + (hash % 9) / 10,
          momentum_loading: ((hash % 10) - 5) / 10,
          r_squared: 0.42 + (hash % 35) / 100
        },
        options_signals: {
          iv_rank: 30 + (hash % 55),
          put_call_ratio_volume: 0.65 + (hash % 70) / 100,
          term_structure: hash % 4 === 0 ? "backwardation" : "normal",
          near_term_event_risk: hash % 4 === 0
        },
        data_quality: {
          fields_requested: 7,
          fields_received: 6,
          quality_score: 0.86,
          fields_missing: mode === "deep" ? ["institutional_delta_pct"] : []
        }
      }
    }
  };
}
