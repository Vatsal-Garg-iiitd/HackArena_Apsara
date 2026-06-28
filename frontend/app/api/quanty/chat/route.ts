import { NextRequest, NextResponse } from "next/server";
import marketData from "@/public/data/market.json";

type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

type ChatRequest = {
  messages?: ChatMessage[];
  page?: string;
};

const llmUrl = process.env.QUANTY_LLM_API_URL || "https://api.openai.com/v1/chat/completions";
const llmModel = process.env.QUANTY_LLM_MODEL || "gpt-4o-mini";

function latestMarketSummary() {
  const indices = marketData.indices
    .map((index) => {
      const topCompanies = index.companies
        .slice(0, 8)
        .map((company) => `${company.name} (${company.symbol}): ${company.price}, ${company.changePercent}%`)
        .join("; ");

      return `${index.name} ${index.symbol}: price ${index.price}, change ${index.change}, change percent ${index.changePercent}%. Constituents: ${topCompanies}`;
    })
    .join("\n");

  return `Market data timestamp: ${marketData.generatedAt}.\n${indices}`;
}

function localAnswer(question: string) {
  const lower = question.toLowerCase();
  const firstIndex = marketData.indices[0];
  const secondIndex = marketData.indices[1];

  if (lower.includes("nifty") || lower.includes("sensex") || lower.includes("market")) {
    return `Current app data shows ${firstIndex.name} at ${firstIndex.price} (${firstIndex.changePercent}%) and ${secondIndex.name} at ${secondIndex.price} (${secondIndex.changePercent}%). For deeper reasoning, add QUANTY_LLM_API_KEY so I can explain trends conversationally.`;
  }

  if (lower.includes("portfolio")) {
    return "Open Portfolio to track saved positions, view allocation, fetch sentiment, and run prediction cards. I can explain those results once you ask about a symbol or metric.";
  }

  if (lower.includes("voice") || lower.includes("speak")) {
    return "Use the mic button to ask by voice. Add SMALLEST_AI_API_KEY and SMALLEST_AI_TTS_URL to enable server-side Quanty voice output.";
  }

  return "I am Quanty, your trading workspace assistant. I can help explain dashboard data, portfolio metrics, sentiment, predictions, and app navigation. Add QUANTY_LLM_API_KEY for full AI reasoning.";
}

async function askLlm(messages: ChatMessage[], page?: string) {
  const key = process.env.QUANTY_LLM_API_KEY;
  if (!key) return null;

  const system: ChatMessage = {
    role: "system",
    content: [
      "You are Quanty, an agentic AI voice chat assistant inside QuantDesk.",
      "Answer clearly and practically. Keep responses concise enough for voice playback.",
      "Use the live app market context when relevant. Say when data is from the app snapshot.",
      `Current page: ${page || "unknown"}.`,
      latestMarketSummary()
    ].join("\n\n")
  };

  const response = await fetch(llmUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`
    },
    body: JSON.stringify({
      model: llmModel,
      messages: [system, ...messages.slice(-10)],
      temperature: 0.35,
      max_tokens: 420
    })
  });

  if (!response.ok) {
    throw new Error("Quanty AI provider request failed.");
  }

  const payload = await response.json();
  return payload?.choices?.[0]?.message?.content as string | undefined;
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as ChatRequest;
    const messages = (body.messages || []).filter((message) => message.content?.trim());
    const latestUserMessage = [...messages].reverse().find((message) => message.role === "user");

    if (!latestUserMessage) {
      return NextResponse.json({ error: "A message is required." }, { status: 400 });
    }

    const llmAnswer = await askLlm(messages, body.page);
    const answer = llmAnswer?.trim() || localAnswer(latestUserMessage.content);

    return NextResponse.json({ answer });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Quanty could not answer right now." },
      { status: 500 }
    );
  }
}
