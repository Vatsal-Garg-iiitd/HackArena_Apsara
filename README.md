# HackArena Apsara — MoE Stock Analysis Pipeline

## What Are We Building?

We are building an **automated, multi-tier stock analysis pipeline** that takes a list of stock tickers (e.g. `AAPL`, `MSFT`) and produces a structured investment signal — split across two time horizons:

- **`tactical_horizon_30d`** → Short-term: should you buy, hold, or sell *right now* based on technicals and momentum?
- **`structural_horizon_1y`** → Long-term: is the company fundamentally healthy enough to hold for months/years?

The system is designed to **replace the work a team of analysts would do in hours** — gathering data, reading filings, scoring earnings calls, computing ratios — and compress it into a structured, explainable signal in seconds.

---

## Why Are We Doing It?

Traditional stock analysis has three major bottlenecks:

1. **Data is scattered** — fundamentals live in SEC filings, technicals in price feeds, sentiment in earnings transcripts, macro context in Federal Reserve databases. No single tool unifies all of this.

2. **Analysts introduce bias** — a human analyst may focus too heavily on narrative ("the CEO sounded confident") and ignore a deteriorating balance sheet. Or vice versa.

3. **LLMs alone hallucinate on numbers** — if you ask a language model to interpret raw financial ratios, it has no reliable grounding. It may confidently state a company is healthy when its debt-to-equity is dangerously high relative to its sector.

Our pipeline solves all three by using a **tiered separation of concerns**:
- Numbers are computed in pure Python, never trusted to an LLM.
- Text is compressed before it hits an LLM, cutting token waste.
- The LLM only interprets pre-computed, peer-normalized signals — not raw numbers.

---

## Architecture: A Tour of Every Layer

### Layer 0 — The Numeric Engine (Pure Python, Zero AI)

This is the foundation. Every metric is computed mathematically. No guessing, no hallucination.

#### Where the data comes from:

| Data Category | Source | Why This Source |
|--------------|--------|----------------|
| Balance sheet (assets, liabilities, equity) | `yfinance` | Free, covers all major US equities, quarterly data |
| Income statement (revenue, margins, EPS) | `yfinance` | Same API, consistent schema |
| Cash flow (operating CF, capex) | `yfinance` | Required for solvency ratios |
| 60-day price history (OHLCV) | `yfinance` | For RSI, MACD, Sharpe, drawdown |
| Insider transactions | `yfinance` | Insider buy/sell counts are a proven smart-money signal |
| Macro indicators (Fed rate, VIX, yield curve) | **FRED API** (Federal Reserve) | The most authoritative source for US macroeconomic data — free, reliable, used by professional quants |
| Factor data (Fama-French 5 factors + Momentum) | **Kenneth French Data Library** | The academic gold standard for factor decomposition, used in every top-tier quant fund |
| Options chain (IV, put/call ratio, term structure) | Data vendor abstraction | Options market implies forward-looking fear/greed more accurately than price alone |
| 13F institutional filings | **SEC EDGAR** | Legally required quarterly disclosures of large institution holdings — directly reveals "smart money" moves |

#### What we compute and why:

**Solvency & Liquidity** — *Can this company survive a downturn?*
- `current_ratio` = Current Assets / Current Liabilities. Below 1.0 means the company cannot cover short-term obligations.
- `quick_ratio` = (Assets − Inventory) / Liabilities. More conservative — excludes illiquid inventory.
- `cash_ratio` = Cash / Liabilities. The harshest liquidity test.
- `debt_equity` = Total Debt / Equity. High values signal overleveraging — dangerous when rates rise.
- `interest_coverage` = EBIT / Interest Expense. Below 1.5x means earnings barely cover interest — near-insolvency risk.
- `working_capital` = Current Assets − Current Liabilities. Absolute dollar buffer for operations.
- `8-quarter trend` = Current Ratio over the last 8 quarters. Trend direction matters more than a single snapshot.

**Asset Efficiency & Turnover** — *Is management using assets productively?*
- `inventory_turnover` = COGS / Inventory. Low turnover = unsold goods piling up — a demand warning.
- `receivables_turnover` = Revenue / Receivables. Low = customers are slow to pay — cash flow risk.
- `DSO` (Days Sales Outstanding) = (Receivables / Revenue) × 90. How many days to collect payment.
- `payables_turnover` = COGS / Payables. Reveals if a company is stretching supplier payments (a liquidity management tactic).

**Profitability** — *Is the core business model working?*
- `gross_margin` = Gross Profit / Revenue. Pure pricing power metric — industry benchmarks differ massively (SaaS ~70%, retail ~25%).
- `operating_margin` = Operating Income / Revenue. After paying for operations — measures operational efficiency.
- `net_margin` = Net Income / Revenue. Bottom-line profitability.
- `ROE` = Net Income / Equity. Return to shareholders — Buffett famously looks for consistent >15% ROE.
- `ROA` = Net Income / Assets. How efficiently assets generate profit.
- `ROCE` = EBIT / Capital Employed. Most comprehensive return metric — accounts for both debt and equity.
- `EPS` = Earnings Per Share. The number analyst consensus forecasts are measured against.

**Technicals** — *What does the price action say right now?*
- `RSI-14` = Relative Strength Index over 14 days. Above 70 = overbought. Below 30 = oversold (potential reversal).
- `MACD` = Moving Average Convergence Divergence. The direction of the MACD histogram signals bullish or bearish momentum shifts.
- `60-day Volatility` = Annualized standard deviation of daily returns. Higher = more risk.
- `Sharpe Ratio` = (Return − Risk-free Rate) / Volatility. Risk-adjusted return — the most widely used performance metric in finance.
- `Max Drawdown` = Largest peak-to-trough price drop. Reveals downside risk exposure.

**Fama-French 5-Factor + Momentum** — *What drives this stock's returns?*

This is the academic backbone of modern quantitative finance. We download factor return data directly from Professor Kenneth French's data library and run an **Ordinary Least Squares (OLS) regression**:

```
Stock Excess Return = α + β₁(Market) + β₂(SMB) + β₃(HML) + β₄(RMW) + β₅(CMA) + β₆(Momentum) + ε
```

- **α (Alpha)** — Return not explained by any factor. Positive, statistically significant alpha is the definition of a genuinely "good stock".
- **Market Beta (β₁)** — Sensitivity to broad market moves. >1 = amplifies market swings.
- **SMB (β₂)** — Small minus Big. Positive loading = acts like a small-cap (historically higher returns but more volatile).
- **HML (β₃)** — High minus Low (value factor). Positive = value stock. Negative = growth stock.
- **RMW (β₄)** — Robust minus Weak (profitability factor). Positive = highly profitable firm.
- **CMA (β₅)** — Conservative minus Aggressive (investment factor). Positive = conservative capital allocator.
- **Momentum (β₆)** — Whether the stock rides recent price trends.
- **R²** — How much variance is explained by the model. Low R² with high alpha = a genuinely idiosyncratic stock.

**Macro Regime** — *Is the economic backdrop supportive or hostile?*

Using the **FRED API** we fetch live:
- **Fed Funds Rate** (FEDFUNDS) — High rates compress valuations, especially for growth stocks.
- **HY OAS** (BAMLH0A0HYM2) — High-yield credit spread. Above 600bps = credit stress / near-recession.
- **Yield Curve Spread** (T10Y3M) — Inverted yield curve has preceded every US recession since the 1960s.
- **VIX** (VIXCLS) — Market fear gauge. Above 25 = high volatility regime.

We classify the regime as `bullish_macro`, `bearish_macro`, or `neutral_macro` and pass a human-readable context string to the LLM so it can adjust its interpretation accordingly.

**Options Signals** — *What does the derivatives market know that equity traders don't?*
- **IV Rank** — Where current implied volatility sits relative to its 52-week range. High IV rank = fear/uncertainty priced in.
- **Put/Call Ratio** — More puts than calls = hedging/bearish sentiment. A contrarian indicator at extremes.
- **IV Term Structure** — If near-term IV > long-term IV ("backwardation"), the market is pricing a near-term event risk (earnings, legal case, product launch).

**Peer Normalization** — *Is the metric actually good relative to competitors?*

A Current Ratio of 1.5 is dangerous for a fast-burning tech startup but perfectly healthy for a utility company. Passing raw numbers to an LLM forces it to apply its own built-in "average company" benchmarks which are wrong for most sectors.

We solve this by computing the **peer group median** for each key metric (solvency, profitability) and passing only the **delta**:

```
Normalized Current Ratio = Ticker Current Ratio − Peer Group Median
```

Positive = better than peers. Negative = worse. This removes regime and sector bias entirely from the LLM's input.

---

### Layer 1A — Quantitative Synthesizer (Gemini Flash)

**Input**: The compact Tier 0 JSON (all numeric metrics, normalized and raw).

**What it does**: The LLM is given strict instructions to treat each data section independently (solvency vs. technicals vs. smart money). It outputs structured reads:
- `solvency_read` → "improving / stable / deteriorating" + rationale
- `efficiency_read` → "efficient / lagging / neutral"
- `profitability_read` → "strong / weak / stable"
- `smart_money_read` → "accumulating / distributing / neutral"
- `technical_read` → "overbought / oversold / neutral"
- `macro_fit` → "tailwind / headwind / neutral"

**Why Gemini Flash**: It is the fastest and cheapest model that supports `response_schema` (native Pydantic enforcement). Structured output means we never need to parse messy JSON strings — the API guarantees the schema is correct.

**Why batch up to 3 tickers**: Testing revealed that Gemini Flash's attention degrades and begins truncating output beyond ~3 tickers in a single prompt.

---

### Layer 1B — Narrative Synthesizer (Gemini Flash)

**Input**: Preprocessed text data — earnings call summary, SEC Item 1A (risk factors), Item 7 (MD&A), recent news headlines.

**Why preprocess before sending to LLM?**

A raw earnings call transcript can be 30,000+ words. Feeding that directly would:
1. Exceed the token budget instantly.
2. Force the LLM to "read" irrelevant boilerplate (legal disclaimers, operator scripts).
3. Cost significantly more in API calls.

Instead we:
- **Segment** the transcript by speaker and role using regex (CEO prepared remarks vs. analyst Q&A).
- **Filter** Q&A turns to only keep those mentioning financially relevant keywords (`guidance`, `margin`, `capex`, `headwind`, etc.).
- **Contextual sweep** the prepared remarks using keyword matching — extracting only the most signal-dense sentences plus their immediate neighbours for context.
- **Sentiment score** the text locally using the Loughran-McDonald financial dictionary (tuned for finance, unlike general-purpose sentiment models which misclassify words like "liability" as negative).

This reduces a 30,000-word transcript to a ~2,000-word structured JSON before it ever touches an LLM.

**Output**: `NarrativeSynthesizerOutput` — news tone, earnings read, guidance direction, outlook/risk flags, competitive position.

---

### Layer 2 — General Expert (Gemini Flash)

**Input**: The Tier 1A quantitative read + Tier 1B narrative read for a single ticker.

**What it does**: Acts as the lead analyst — merging quant and narrative signals into a final verdict. Critically, it is explicitly instructed to **not average conflicting signals**. If technicals say sell but fundamentals say buy, it must name the conflict and explain which dominates and why.

**Output**:
```json
{
  "ticker": "AAPL",
  "signals": {
    "tactical_horizon_30d": "hold",
    "structural_horizon_1y": "buy"
  },
  "confidence": "high",
  "rationale": "...",
  "conflicting_signals": ["..."]
}
```

The separation into two horizons is critical: a bearish MACD (5-day signal) and a rock-solid balance sheet (1-year signal) are not contradictory — they operate on completely different time scales and should produce independent outputs.

---

### Caching Strategy

LLM calls cost time and API quota. We cache aggressively:

| Tier | Cache Key | TTL Logic |
|------|----------|----------|
| Tier 1A (Quant) | `{ticker}:{date}:quant_v1` | Daily — re-runs every market day |
| Tier 1B (Narrative) | `{ticker}:{quarter}:narrative_v1` | Quarterly — only re-runs on new earnings/filings |
| Tier 2 (Expert) | `{ticker}:{date}:general_v1` | Daily |

The cache backend is **SQLite** — thread-safe, handles concurrent async writes natively, and cannot be corrupted by race conditions the way flat JSON files can.

---

### Backtesting

The `SignalBacktester` allows historical validation of any signal the pipeline produces. Given a price series and a signal series (1=buy, -1=sell, 0=hold), it computes:

- **Annualized Return** — Projected yearly gain from acting on signals.
- **Sharpe Ratio** — Risk-adjusted return. Above 1.0 is considered good; above 2.0 is exceptional.
- **Max Drawdown** — Worst peak-to-trough loss. A signal with a 40% Max Drawdown is unusable for most portfolios.
- **Calmar Ratio** — Annualized Return / |Max Drawdown|. Measures how much return you get per unit of worst-case risk.
- **Win Rate** — % of trades that were profitable.
- **Walk-Forward Validation** — Splits data into in-sample (training) and out-of-sample (test) periods to detect overfitting. If in-sample Sharpe >> out-of-sample Sharpe, the signal is likely overfit to historical noise.
- **Monte Carlo Significance** — Shuffles signal dates randomly 1,000 times. If the actual signal beats 95% of random portfolios, it is statistically significant (p < 0.05).
- **Horizon Optimization** — Tests holding periods of 5, 10, 21, 42, 63, 126, 252 days to find the empirically optimal horizon for each signal.

---

## How to Run

### 1. Setup
```bash
git clone https://github.com/Vatsal-Garg-iiitd/HackArena_Apsara.git
cd HackArena_Apsara
pip install -r requirements.txt
```

### 2. Configure API Key
Create a `.env` file in the project root:
```
GEMINI_API_KEY=your_key_here
```

### 3. Run Analysis
```bash
# Single ticker
python main.py --tickers AAPL

# Multiple tickers
python main.py --tickers AAPL,MSFT,GOOGL

# Force refresh (ignore cache)
python main.py --tickers AAPL --refresh-all
```

### 4. Output
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "signals": {
      "tactical_horizon_30d": "hold",
      "structural_horizon_1y": "buy"
    },
    "confidence": "high",
    "rationale": "Strong long-term fundamentals...",
    "conflicting_signals": ["Bearish MACD conflicts with positive insider accumulation..."]
  }
}
```

---

## Key Design Decisions

| Decision | Rationale |
|---------|----------|
| **Tier 0 is LLM-free** | Numbers must be exact. LLMs cannot reliably compute ratios or run regressions. All math stays in Python. |
| **Peer normalization before LLM** | A 1.5 current ratio is meaningless without industry context. Normalize first, interpret second. |
| **Structured output (response_schema)** | Eliminates JSON parsing failures. Pydantic guarantees the schema at the API boundary. |
| **Max 3 tickers per LLM batch** | Empirically determined: Gemini Flash truncates output beyond 3 tickers in one prompt. |
| **Separate tactical vs. structural signals** | Different holding periods must not be averaged. A 5-day technical signal and a 1-year fundamental signal are orthogonal dimensions. |
| **SQLite cache** | Flat JSON files cannot handle concurrent async writes. SQLite's WAL mode handles this natively. |
| **FRED for macro** | Yahoo Finance macro data is unreliable. FRED is the official Federal Reserve database — trusted by every professional quant desk. |
| **Kenneth French for factors** | The Fama-French factor library is the academic standard — directly comparable to any published quant research. |
| **Preprocessing before LLM for text** | Reduces a 30,000-word transcript to ~2,000 words before it touches the API. Saves quota, improves signal quality. |
