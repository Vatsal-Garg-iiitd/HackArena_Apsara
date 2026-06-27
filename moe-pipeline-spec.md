# Free-Tier Multi-Expert Stock Analysis Pipeline — Build Spec

## 0. Context for whoever (whatever) is building this

This is a MoE-style multi-agent stock analysis system, inspired by **TradExpert** (arXiv:2411.00782) and **MarketSenseAI 2.0** (arXiv:2502.00415), redesigned to run entirely on **free-tier Gemini** (Flash / Flash-Lite — Pro was pulled from the free tier in April 2026 and is paid-only now) with no local GPU.

The original papers use one LLM call per "expert" (news, fundamentals, solvency, investor behavior, macro, competitive intel, future prospects, dynamics/peer-comparison...). That's 8-10 calls per ticker per run. On a free tier with single-digit-to-low-teens RPM and a few hundred to ~1500 RPD (varies by model, **check Google AI Studio for current numbers before building anything that depends on exact limits — these change without notice**), that blows the budget almost immediately.

The fix: collapse everything into **3 LLM calls per ticker** plus **one pure-code numeric layer**, and decouple refresh frequency from call count so most experts don't even run daily.

**Hard constraints to design around:**
- No local model, no GPU. Gemini Flash / Flash-Lite only, via API.
- Free tier only — assume Pro is unavailable unless the user explicitly says they've enabled billing.
- Minimize wall-clock build time — this is a hackathon project. Do not introduce infra (Redis, Postgres, message queues) that a flat-file/SQLite cache can replace. Simplicity > architectural purity.
- Minimize wall-clock *run* time — caching and batching are not optional nice-to-haves, they are the actual performance strategy.

---

## 1. Architecture Overview (text, no diagram — described linearly)

```
Raw data sources (yfinance / EDGAR / OpenBB / earnings transcripts / news)
        │
        ▼
┌─────────────────────────────────────────────┐
│ TIER 0 — Numeric Engine (pure code, no LLM)  │
│ ratios, deltas, technicals, peer comparison  │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ PREPROCESSING — Earnings call pipeline       │
│ (pure code, no LLM — see Section 3)          │
└─────────────────────────────────────────────┘
        │
   ┌────┴────┐
   ▼         ▼
┌────────┐ ┌──────────────┐
│ TIER 1A│ │   TIER 1B    │
│ Quant  │ │  Narrative   │
│ Synth  │ │  Synth       │
│(1 call)│ │  (1 call)    │
└───┬────┘ └──────┬───────┘
    └──────┬───────┘
           ▼
   ┌───────────────┐
   │   TIER 2       │
   │ General Expert │
   │   (1 call)     │
   └───────────────┘
           ▼
     Final signal (buy/hold/sell + rationale)
```

**Call budget per ticker, steady state:** 1-3 LLM calls/day, not 8-10. Tier 1B (Narrative) only re-runs when a new filing or earnings call drops — most days it's a cache hit, not a call.

---

## 2. Tier 0 — Numeric Engine (zero LLM calls)

Everything here is arithmetic on structured data. No model ever sees raw numbers for this tier — they get computed once and handed downstream as compact JSON.

### 2.1 What it computes
| Category | Specific metrics | Source |
|---|---|---|
| Solvency & liquidity | current ratio, quick ratio, debt/equity, interest coverage, 8-quarter trend | `yfinance`, SimFin |
| Investor behavior | 13F position deltas (QoQ), insider buy/sell counts (90d), short interest % change | EDGAR, OpenBB |
| Technical/alpha factors | RSI, MACD, realized volatility, Sharpe, max drawdown (60d) | `yfinance` OHLCV |
| Dynamics (numeric half) | peer-relative Sharpe/vol/drawdown vs. 3-5 named competitors | `yfinance`, OpenBB |

### 2.2 Output schema (per ticker)
```json
{
  "ticker": "string",
  "as_of": "YYYY-MM-DD",
  "solvency": {"current_ratio": 0.0, "quick_ratio": 0.0, "debt_equity": 0.0, "interest_coverage": 0.0, "trend_8q": [0.0, ...]},
  "investor_behavior": {"institutional_delta_pct": 0.0, "insider_buys_90d": 0, "insider_sells_90d": 0, "short_interest_delta_pct": 0.0},
  "technical": {"rsi_14": 0.0, "macd_signal": "string", "volatility_60d": 0.0, "sharpe_60d": 0.0, "max_drawdown_60d": 0.0},
  "peer_dynamics": {"peer_tickers": ["string"], "relative_sharpe": 0.0, "relative_volatility": 0.0, "relative_drawdown": 0.0}
}
```

### 2.3 Implementation notes
- Pure `pandas`. No async needed here — it's fast enough to run synchronously.
- This is also the **batching-safe** tier: stuff 20-50 tickers' worth of this JSON into one downstream LLM call without any accuracy risk, since it's compact numeric data, not prose.
- Refresh: daily before market open, or on-demand. Cheap enough to just always recompute — don't bother caching this tier unless API rate limits on the data source itself force it.

---

## 3. Earnings Call Preprocessing — No LLM (this is the part that was explicitly asked for)

**Goal:** turn a 10,000-20,000+ word raw transcript into a small, structured, LLM-ready summary *without spending a single model call on it.* This matters for two reasons: (1) it's free, (2) it directly prevents the "lost-in-the-middle" / TPM-overflow problem in Tier 1B by ensuring the Narrative Synthesizer never sees raw transcript text.

### 3.1 Data source (needs to be picked before building — verify free-tier coverage at build time)
None of these were confirmed free-and-sufficient as of this writing — treat as candidates to test, not guarantees:
- **Finnhub** — has an earnings-transcript endpoint; check current free-tier rate limit/coverage.
- **API Ninjas** (`/v1/earningstranscriptsearch`, `/v1/earningstranscript...`) — covers 8,000+ companies, returns speaker-segmented transcripts and even pre-extracted `summary`/`guidance`/`risk_factors` fields. Verify free-tier request quota before relying on it.
- **Financial Modeling Prep** — has a transcript endpoint; unclear if it's free-tier or premium-gated. Verify.
- Seeking Alpha / Motley Fool — readable, but no public free API; scraping these has ToS implications, don't build around it without checking their terms first.

**Action item for Claude Code:** write a thin `TranscriptSource` interface so whichever API wins can be swapped in without touching the rest of the pipeline.

### 3.2 Pipeline steps (all pure Python, zero API calls to an LLM)

**Step 1 — Speaker & section segmentation (regex)**
Most transcripts follow a consistent pattern: `Name - Title:` or `Name (Title):` or an all-caps name line followed by a colon, then prose until the next speaker label. Also detect the prepared-remarks/Q&A boundary via a fixed phrase match (e.g. "question-and-answer session", "first question comes from", "I'll now turn the call over to the operator").
```python
SPEAKER_PATTERN = re.compile(r'^([A-Z][a-zA-Z.\' -]+)\s*[-–(]\s*([^:)]+)[):]\s*(.*)', re.MULTILINE)
QA_BOUNDARY_PATTERNS = [
    r"question.and.answer session",
    r"first question (comes|will come) from",
    r"we('ll| will) now (begin|open) the (question|q&a)",
]
```
Output: a list of `{speaker, role_raw, section: "prepared"|"qa", text}` turns.

**Step 2 — Boilerplate / safe-harbor stripping**
Forward-looking-statement disclaimers are near-identical across calls. Maintain a small list of boilerplate trigger phrases ("forward-looking statements", "safe harbor", "actual results may differ materially", "non-GAAP financial measures") and drop any paragraph whose sentence matches one of these above a fuzzy-match threshold (use `rapidfuzz`, threshold ~85). This alone typically removes 5-10% of transcript length for free.

**Step 3 — Speaker role normalization**
Map raw titles to a small fixed taxonomy: `CEO`, `CFO`, `COO`, `IR`, `Operator`, `Analyst`. Use simple keyword matching on the title string ("chief executive" → CEO, "chief financial" → CFO, "investor relations" → IR, analyst firm names appearing in the Q&A participant list → Analyst). No LLM needed — earnings call title strings are extremely formulaic.

**Step 4 — Q&A relevance filtering (keyword gate)**
Before any further processing, drop Q&A turns that don't contain at least one term from a finance-salience keyword list: `guidance, margin, headwind, tailwind, capex, opex, growth, churn, backlog, buyback, dividend, pricing, demand, supply, inventory, outlook, forecast`. This discards small talk, thank-yous, and operator filler — typically cuts Q&A volume by 30-50% before it ever reaches a model.

**Step 5 — Lexicon-based sentiment scoring**
Use the **Loughran-McDonald** finance-specific word list (positive/negative/uncertainty/litigious categories — this is the standard finance-NLP sentiment dictionary, freely available) to score each remaining paragraph. Output a numeric sentiment vector per section (`{positive_count, negative_count, uncertainty_count, litigious_count, net_sentiment}`). This is a dictionary lookup, not a model call.

**Step 6 — Extractive condensation (TF-IDF / TextRank, not abstractive)**
For the prepared-remarks section, run TextRank (via `sumy` or `gensim`'s `summarize`) keyed off a small set of topic anchor terms (`guidance`, `margin`, `competition`, `outlook`) to pull the most central 3-5 sentences per topic bucket. This is unsupervised graph-based sentence ranking — no LLM, no abstractive rewriting, just picks the most representative existing sentences.

**Step 7 — Deduplication across quarters**
Operator scripts and IR intros repeat almost verbatim quarter to quarter. Hash each paragraph (after lowercasing/whitespace-normalizing) and drop exact-duplicate paragraphs seen in a prior quarter's cache for the same ticker.

### 3.3 Final output schema (this is what Tier 1B actually sees — never the raw transcript)
```json
{
  "ticker": "string",
  "quarter": "2026Q1",
  "call_date": "YYYY-MM-DD",
  "prepared_remarks_excerpts": {
    "guidance": ["sentence", "..."],
    "margin": ["sentence", "..."],
    "outlook": ["sentence", "..."],
    "competition": ["sentence", "..."]
  },
  "qa_excerpts": [
    {"analyst_firm": "string", "question": "sentence", "answer": "sentence", "speaker_role": "CFO"}
  ],
  "sentiment": {"positive": 0, "negative": 0, "uncertainty": 0, "litigious": 0, "net_sentiment": 0.0},
  "token_estimate": 0
}
```
This should land in the **low thousands of tokens**, not tens of thousands — that's the entire point.

### 3.4 Library list
`re` (stdlib), `rapidfuzz` (boilerplate fuzzy match), `sumy` or `gensim` (TextRank/TF-IDF extraction), a static Loughran-McDonald word-list file (no package needed, just a text file), `nltk.sent_tokenize` or a regex sentence splitter for chunking.

---

## 4. Tier 1A — Quant Synthesizer (1 LLM call)

**Model:** Gemini Flash (or Flash-Lite if accuracy holds up in testing — try Lite first, it's cheaper on quota).
**Inputs:** Tier 0 JSON (Section 2.2) for one or more tickers, plus current macro snapshot (rates, inflation, yield curve — pull from FRED's free API, no LLM needed there either).
**Batching:** Safe to batch many tickers (10-30+) into one call — this is pure numeric interpretation.
**Refresh cadence:** Daily.

### Prompt template
```
SYSTEM: You are a quantitative analyst. For each ticker below, you have four
independent data sections. Reason about EACH section using ONLY the data in
that section — do not let one section's data influence another's interpretation.
Output ONLY valid JSON, no prose outside the JSON.

For ticker {TICKER}:
[SOLVENCY] {solvency_json}
[INVESTOR_BEHAVIOR] {investor_behavior_json}
[TECHNICAL] {technical_json}
[MACRO_CONTEXT] {macro_json}

Repeat for each ticker in the batch.

Output schema per ticker:
{
  "ticker": "...",
  "solvency_read": {"trend": "improving|stable|deteriorating", "rationale": "..."},
  "smart_money_read": {"signal": "accumulating|distributing|neutral", "rationale": "..."},
  "technical_read": {"signal": "overbought|oversold|neutral", "rationale": "..."},
  "macro_fit": {"tailwind|headwind|neutral": "...", "rationale": "..."}
}
Return a JSON array, one object per ticker. Nothing else.
```

---

## 5. Tier 1B — Narrative Synthesizer (1 LLM call, infrequent)

**Model:** Gemini Flash (use the full model here, not Lite — qualitative synthesis benefits more from reasoning quality than the numeric tier does).
**Inputs:** earnings-call preprocessing output (Section 3.3), extracted 10-K MD&A/competitive sections (use the same kind of regex section-extraction as the earnings pipeline — 10-Ks are SEC-structured, Item 7 = MD&A, Item 1A = risk factors — extract those sections only, never feed a full 10-K), and a small set of recent news headlines/snippets (not full articles).
**Batching:** **Do not batch tickers here.** One ticker per call, or at most 2-3 if their combined preprocessed payload stays small (low thousands of tokens). This is the tier where stuffing too much in causes lost-in-the-middle degradation and risks the per-minute token cap. The whole point of Section 3 was to keep this call's input small — don't undo that by batching tickers back in.
**Refresh cadence:** Only when a new earnings call or filing drops for that ticker. Cache everything else. This is the single biggest "don't waste time/quota" lever in the system — most days, this tier doesn't run at all.

### Prompt template
```
SYSTEM: You are a qualitative research analyst. You have four independent
text sections for {TICKER}. Reason about each section independently using
only its own data. Output ONLY valid JSON.

[NEWS] {news_snippets}
[EARNINGS_CALL] {earnings_preprocessed_json}
[FILING_OUTLOOK] {mdna_extract}
[COMPETITIVE] {competitor_extract}

Output schema:
{
  "ticker": "...",
  "news_sentiment": {"tone": "positive|negative|mixed|neutral", "key_drivers": ["..."]},
  "earnings_read": {"tone": "...", "guidance_direction": "raised|maintained|lowered|none_given", "key_quotes_paraphrased": ["..."]},
  "outlook": {"summary": "...", "risk_flags": ["..."]},
  "competitive_position": {"summary": "...", "relative_strength": "gaining|losing|stable"}
}
```

---

## 6. Tier 2 — General Expert (1 LLM call)

**Model:** Gemini Flash.
**Inputs:** Tier 1A JSON + Tier 1B JSON (both already compact — this call's input is small regardless of how much raw data fed the earlier tiers).
**Batching:** Moderate batching is fine here (5-10 tickers) since inputs are pre-compressed JSON, not prose.
**Refresh cadence:** Daily (even on days Tier 1B is cached, Tier 2 re-runs with fresh Tier 1A + cached Tier 1B).

### Prompt template
```
SYSTEM: You are the lead analyst. Merge the quantitative and qualitative
reports below into one signal. If they conflict, say so explicitly rather
than averaging them away.

[QUANT_REPORT] {tier1a_json}
[NARRATIVE_REPORT] {tier1b_json}

Output ONLY:
{
  "ticker": "...",
  "signal": "buy|hold|sell",
  "confidence": "low|medium|high",
  "rationale": "2-4 sentences",
  "conflicting_signals": ["..."] // empty array if none
}
```

---

## 7. Rate-limit & quota management

- **Verify live limits before writing retry logic against assumed numbers.** As of mid-2026, Pro is paid-only; Flash/Flash-Lite retain free tiers but the exact RPM/RPD/TPM figures have changed multiple times this year and vary by model — check Google AI Studio's quota page for the live numbers on the actual project being used.
- Use an async queue with a semaphore capping concurrency at 1-2 in-flight requests — don't fire all tickers' calls in parallel.
- Exponential backoff with jitter on HTTP 429.
- Track remaining quota from response headers if available rather than estimating by call count.
- TPM is usually the binding constraint, not RPD, once batching is in place — keep an eye on total tokens per call, not just call count.
- If working with teammates for a hackathon: separate Google Cloud projects (one per teammate's account) get independent quota pools. Multiple API keys *within the same project* do not — they share one pool.

## 8. Caching & refresh cadence (the actual speed lever)

| Tier | Refresh trigger | Cache key |
|---|---|---|
| Tier 0 (numeric) | Always recompute (cheap) | n/a |
| Earnings preprocessing | New earnings call only | `{ticker}:{quarter}:earnings_v1` |
| Tier 1A (Quant) | Daily | `{ticker}:{date}:quant_v1` |
| Tier 1B (Narrative) | New filing/earnings call only | `{ticker}:{quarter}:narrative_v1` |
| Tier 2 (General) | Daily | `{ticker}:{date}:general_v1` |

Implementation: a flat JSON-file or SQLite cache is sufficient for a hackathon — don't reach for Redis. Check cache before any LLM call; only call if the key is absent or stale per the trigger column above. On a normal day, only Tier 0 + Tier 1A + Tier 2 actually execute — Tier 1B and earnings preprocessing are cache hits unless something new dropped.

## 9. Suggested project structure
```
/pipeline
  /tier0_numeric/
    ratios.py
    investor_signals.py
    technicals.py
    peer_dynamics.py
  /preprocessing/
    earnings_call/
      source.py          # TranscriptSource interface + chosen implementation
      segment.py          # Step 1
      boilerplate.py       # Step 2
      roles.py             # Step 3
      qa_filter.py          # Step 4
      sentiment_lexicon.py   # Step 5 (+ loughran_mcdonald.txt data file)
      extractive.py         # Step 6
      dedup.py              # Step 7
    filings/
      sec_section_extract.py  # Item 7 / Item 1A extraction from 10-Ks
  /tier1_llm/
    quant_synthesizer.py
    narrative_synthesizer.py
  /tier2_llm/
    general_expert.py
  /infra/
    rate_limiter.py     # semaphore + backoff
    cache.py             # SQLite/JSON cache wrapper
    gemini_client.py      # thin wrapper around the API call
  /schemas/
    *.py (pydantic models matching the JSON schemas above)
  orchestrator.py        # LangGraph graph wiring it all together
  main.py
```

## 10. Build order (optimized for limited time)

1. Tier 0 numeric engine + cache layer first — it's pure code, no API keys needed to test, and everything downstream depends on its output shape.
2. `infra/cache.py` and `infra/rate_limiter.py` next — build these before any LLM call so every subsequent tier is cache-aware and rate-limit-safe from the start, instead of retrofitting it later.
3. Earnings call preprocessing (Section 3) — pick ONE transcript source, get the regex segmentation working on a real sample transcript before building the rest of the steps on top of it.
4. Tier 1A (Quant Synthesizer) — simplest LLM tier, good smoke test for the Gemini client wrapper.
5. SEC filing section extraction (10-K MD&A/risk factors) — same regex-extraction pattern as earnings calls, reuse what you learned there.
6. Tier 1B (Narrative Synthesizer).
7. Tier 2 (General Expert) + orchestrator wiring everything together.
8. Only after the above works end-to-end on 1-2 tickers: add multi-ticker batching to Tier 0/1A/2.

## 11. Open questions to resolve before/while building
- Which earnings-transcript source actually has a usable free tier at the volume needed? (Section 3.1 — test, don't assume.)
- Confirm current Gemini free-tier RPM/RPD/TPM for whichever exact model string is used.
- Decide whether Flash-Lite is accurate enough for Tier 1A, or whether full Flash is needed there too (test both, Lite is cheaper on quota if it holds up).
