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

function toGeminiText(messages: ChatMessage[]) {
  return messages.map((message) => `${message.role.toUpperCase()}: ${message.content}`).join("\n\n");
}

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
    return `Current app data shows ${firstIndex.name} at ${firstIndex.price} (${firstIndex.changePercent}%) and ${secondIndex.name} at ${secondIndex.price} (${secondIndex.changePercent}%). The dashboard snapshot is slightly positive, so scan the index constituents, portfolio exposure, and prediction cards before taking a directional view.`;
  }

  if (lower.includes("portfolio")) {
    return "In Portfolio, you can track saved positions, allocation, sentiment, and prediction cards. Ask about a symbol, health status, volatility, strike price, or prediction result and I will explain the values from the saved snapshot.";
  }

  if (lower.includes("voice") || lower.includes("speak") || lower.includes("mic") || lower.includes("microphone")) {
    return "Use the mic button to record your question. Quanty writes the recording into text, sends that text to chat, and then reads the answer back when voice output is available.";
  }

  if (lower.includes("dashboard")) {
    return `The dashboard is using the latest app snapshot from ${marketData.generatedAt}. ${firstIndex.name} is at ${firstIndex.price}, while ${secondIndex.name} is at ${secondIndex.price}. Use the dashboard to compare index movement, top constituents, and market direction.`;
  }

  if (lower.includes("sentiment")) {
    return "Sentiment helps you compare market mood against price movement. Use it as context, not a standalone signal: confirm it with portfolio exposure, prediction output, and recent index moves.";
  }

  if (lower.includes("prediction") || lower.includes("predict")) {
    return "Prediction cards use the saved stock snapshot and historical candles to estimate option-style outcomes. Check spot price, strike price, volatility, risk-free rate, and the selected option type before interpreting the result.";
  }

  return "I am Quanty, your trading workspace assistant. I can explain dashboard data, portfolio metrics, sentiment, predictions, voice controls, and app navigation using the current app snapshot.";
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

  if (llmUrl.includes("generativelanguage.googleapis.com")) {
    const response = await fetch(llmUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-goog-api-key": key
      },
      body: JSON.stringify({
        contents: [
          {
            role: "user",
            parts: [{ text: toGeminiText([system, ...messages.slice(-10)]) }]
          }
        ],
        generationConfig: {
          temperature: 0.35,
          maxOutputTokens: 420
        }
      })
    });

    if (!response.ok) {
      const details = await response.text();
      console.error("Quanty Gemini request failed", response.status, details);
      return null;
    }

    const payload = await response.json();
    return payload?.candidates?.[0]?.content?.parts
      ?.map((part: { text?: string }) => part.text)
      .filter(Boolean)
      .join("\n") as string | undefined;
  }

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
    const details = await response.text();
    console.error("Quanty AI provider request failed", response.status, details);
    return null;
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

    const llmAnswer = await askLlm(messages, body.page).catch((error) => {
      console.error("Quanty AI provider request failed", error);
      return null;
    });
    const answer = llmAnswer?.trim() || localAnswer(latestUserMessage.content);

    return NextResponse.json({ answer });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Quanty could not answer right now." },
      { status: 500 }
    );
  }
}
