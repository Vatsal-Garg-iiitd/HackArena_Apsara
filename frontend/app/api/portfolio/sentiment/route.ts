import { NextRequest, NextResponse } from "next/server";

type RedditChild = {
  data?: {
    title?: string;
    selftext?: string;
    body?: string;
    subreddit?: string;
    permalink?: string;
    score?: number;
    num_comments?: number;
    created_utc?: number;
  };
};

const positiveWords = [
  "beat",
  "bullish",
  "buy",
  "growth",
  "healthy",
  "long",
  "moon",
  "outperform",
  "profit",
  "rally",
  "strong",
  "upside"
];

const negativeWords = [
  "bearish",
  "crash",
  "debt",
  "decline",
  "downside",
  "fraud",
  "loss",
  "miss",
  "risk",
  "sell",
  "short",
  "weak"
];

function scoreText(text: string) {
  const lower = text.toLowerCase();
  const positive = positiveWords.reduce((count, word) => count + (lower.includes(word) ? 1 : 0), 0);
  const negative = negativeWords.reduce((count, word) => count + (lower.includes(word) ? 1 : 0), 0);
  return positive - negative;
}

function sentimentLabel(score: number) {
  if (score > 1) return "Positive";
  if (score < -1) return "Negative";
  return "Neutral";
}

async function redditSearch(query: string) {
  const userAgent = process.env.REDDIT_USER_AGENT || "QuantDeskSentiment/1.0";
  const url = new URL("https://www.reddit.com/search.json");
  url.searchParams.set("q", query);
  url.searchParams.set("sort", "new");
  url.searchParams.set("t", "week");
  url.searchParams.set("limit", "12");

  const response = await fetch(url, {
    headers: {
      "User-Agent": userAgent
    },
    next: {
      revalidate: 300
    }
  });

  if (!response.ok) {
    throw new Error("Reddit sentiment fetch failed.");
  }

  const payload = await response.json();
  return (payload?.data?.children ?? []) as RedditChild[];
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as { symbol?: string; name?: string; ticker?: string | null };
    const symbol = body.symbol?.replace(/\.(NS|BO)$/i, "") || body.ticker || "";
    const company = body.name || symbol;

    if (!symbol && !company) {
      return NextResponse.json({ error: "A stock symbol or company name is required." }, { status: 400 });
    }

    let results: RedditChild[] = [];
    let sourceStatus = "reddit";

    try {
      results = await redditSearch(`"${company}" OR "${symbol}" stock`);
    } catch {
      sourceStatus = "reddit-unavailable";
    }
    const mentions = results.map((child) => {
      const data = child.data ?? {};
      const text = [data.title, data.selftext, data.body].filter(Boolean).join(" ");
      const score = scoreText(text);

      return {
        title: data.title || data.body?.slice(0, 120) || "Reddit mention",
        subreddit: data.subreddit || "reddit",
        url: data.permalink ? `https://www.reddit.com${data.permalink}` : "https://www.reddit.com/search",
        score: data.score ?? 0,
        comments: data.num_comments ?? 0,
        sentiment: sentimentLabel(score),
        sentiment_score: score,
        created_at: data.created_utc ? new Date(data.created_utc * 1000).toISOString() : null
      };
    });

    const totalScore = mentions.reduce((sum, item) => sum + item.sentiment_score, 0);
    const averageScore = mentions.length ? totalScore / mentions.length : 0;
    const positive = mentions.filter((item) => item.sentiment === "Positive").length;
    const negative = mentions.filter((item) => item.sentiment === "Negative").length;
    const neutral = mentions.length - positive - negative;

    return NextResponse.json({
      symbol,
      company,
      source: sourceStatus,
      trend_source: process.env.PYTRENDS_ENABLED === "true" ? "pytrends-configured" : "pytrends-not-configured",
      summary: {
        label: sentimentLabel(averageScore),
        score: averageScore,
        mentions: mentions.length,
        positive,
        neutral,
        negative
      },
      mentions: mentions.slice(0, 6)
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to fetch sentiment." },
      { status: 500 }
    );
  }
}
