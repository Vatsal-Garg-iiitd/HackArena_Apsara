# HackArena Pipeline Explanation

## 1. What This Pipeline Does

HackArena is a multi-tier stock analysis pipeline. The user gives one or more ticker symbols, such as `AAPL`, `MSFT`, or `RELIANCE.NS`, and the system produces a structured investment view with two different horizons:

- `tactical_horizon_30d`: short-term market signal based on price action, momentum, volatility, raw OHLCV behavior, and recent narrative context.
- `structural_horizon_1y`: longer-term business-quality signal based on solvency, profitability, efficiency, macro context, peer comparison, and qualitative narrative.

The key design idea is separation of responsibility:

- Python code computes numbers from raw data.
- Preprocessors compress messy text into structured evidence.
- LLMs interpret already-grounded evidence instead of inventing calculations.
- A final expert LLM merges the independent reads and explicitly names conflicts.

This prevents the most common failure mode in financial LLM systems: asking a model to both calculate financial metrics and reason about them. In this pipeline, the model receives computed evidence and is asked to interpret it.

## 2. High-Level Flow

The main orchestration happens in `pipeline/orchestrator.py`.

For each requested ticker:

1. Tier 0 computes numeric metrics with pure Python.
2. Tier 1A converts Tier 0 numeric metrics into a quant analyst read.
3. Tier 1B gathers recent news and earnings-call context, preprocesses text, and creates a qualitative read.
4. Tier 1C analyzes raw yfinance OHLCV data directly and runs Moirai 1.1-R forecasting when the optional model stack is installed.
5. Tier 2 merges Tier 1A, Tier 1B, Tier 1C, macro context, and consistency warnings into the final signal.
6. The pipeline records cache hits, failures, timing, and run summaries.

The shape is:

```text
Tickers
  |
  v
Tier 0: numeric engine
  |        \
  |         -> macro / peer / factor / options context
  v
Tier 1A: quant synthesizer

Ticker
  |
  v
News + earnings-call preprocessing
  |
  v
Tier 1B: narrative synthesizer

Ticker
  |
  v
Raw yfinance OHLCV
  |
  v
Tier 1C: raw OHLCV analyzer + Moirai 1.1-R forecaster

Tier 1A + Tier 1B + Tier 1C + macro + consistency checks
  |
  v
Tier 2: general expert final signal
```

## 3. What Dataset We Use

There is no single static CSV dataset. The pipeline uses live or cached market and company data from multiple sources.

### 3.1 yfinance

yfinance is the primary market and company data source. It is used through `pipeline/infra/data_vendor.py`, which wraps raw yfinance calls behind a vendor interface.

We use yfinance for:

- OHLCV price history: `Open`, `High`, `Low`, `Close`, `Volume`.
- Financial statements: quarterly balance sheet, income statement, and cash flow statement.
- Company metadata: sector, industry, market cap, and other info fields.
- Insider transactions where available.
- Options chains where available.

This is the main dataset for Tier 0 and Tier 1C.

### 3.2 FRED

FRED data is fetched in:

- `pipeline/tier0_numeric/macro_regime.py`
- `pipeline/tier0_numeric/technicals.py`

We use FRED for macro and risk-free-rate context:

- `FEDFUNDS`: Federal Funds Rate.
- `BAMLH0A0HYM2`: high-yield credit spread.
- `T10Y3M`: 10-year minus 3-month Treasury spread.
- `VIXCLS`: VIX volatility index.
- `TB3MS`: 3-month Treasury Bill rate for risk-free-rate assumptions.

The macro module turns these into a regime label such as `bullish_macro`, `neutral_macro`, or `bearish_macro`.

### 3.3 Kenneth French Data Library

`pipeline/tier0_numeric/factor_model.py` downloads daily factor data from Kenneth French's data library:

- Fama-French 5 factors: market, size, value, profitability, investment.
- Momentum factor.
- Risk-free rate from the factor dataset.

The pipeline aligns stock returns with factor returns and runs an OLS regression to estimate factor exposures and alpha.

### 3.4 Tavily

`pipeline/infra/tavily_client.py` uses Tavily for recent financial news when `TAVILY_API_KEY` is configured.

It searches recent weekly news for each ticker across finance-oriented domains such as Reuters, CNBC, MarketWatch, Yahoo Finance, Barron's, FT, and similar sources. The output is normalized into:

- title
- URL
- publisher
- content
- snippet
- search score
- formatted text for the narrative synthesizer

If the API key is missing, the pipeline returns an explicit "news unavailable" message rather than pretending it has news.

### 3.5 Finnhub Or Mock Earnings Transcripts

`pipeline/preprocessing/earnings_call/source.py` defines transcript sources:

- Finnhub transcript source when `FINNHUB_API_KEY` is configured.
- Mock transcript source as a fallback for testing and demos.

The transcript preprocessing lives in `pipeline/preprocessing/earnings_call/`.

It segments transcripts, extracts prepared remarks, filters relevant Q&A, and computes financial sentiment before the LLM sees the text.

### 3.6 Gemini

Gemini is not a data source. It is the reasoning engine used for structured interpretation.

The code uses `gemini-2.5-flash` through `pipeline/infra/gemini_client.py` for:

- Tier 1A quant interpretation.
- Tier 1B narrative interpretation.
- Tier 2 final synthesis.

The pipeline sends Pydantic schemas to Gemini, so the response is expected to match structured output models rather than free-form prose.

## 4. Data Vendor Layer

The data vendor abstraction is in `pipeline/infra/data_vendor.py`.

It defines a `DataVendorClient` interface with methods:

- `get_financials(ticker, period)`
- `get_ohlcv(ticker, start, end)`
- `get_info(ticker)`
- `get_insider_transactions(ticker)`
- `get_options_chain(ticker)`

The concrete implementation is `YFinanceVendor`. It uses yfinance directly but returns `None` on failure instead of fake zero values.

This matters because a missing current ratio should not become `0.0`. A zero value would look like a terrible balance sheet, while missing data means the pipeline should lower confidence or skip that field.

The vendor is wrapped by `CachedDataVendor`, which caches OHLCV data and only fetches deltas when it already has historical data locally.

## 5. Cache Layer

Caching is implemented in `pipeline/infra/cache.py`.

The cache has two possible backends:

- PostgreSQL, if `DATABASE_URL` is configured.
- SQLite fallback in `.pipeline_cache/cache.db`.

The cache stores:

- generic pipeline outputs by key
- OHLCV rows
- run history
- optional structured tables for financials, transcripts, and signals in the PostgreSQL backend

Important cache keys in the current orchestrator:

- Tier 1A: `{ticker}:{today}:quant_v2`
- Tier 1B: `{ticker}:{quarter}:narrative_v2`
- Tier 1C: `{ticker}:{today}:ohlcv_v1`
- Tier 2: `{ticker}:{today}:general_v3`

This means:

- Quant and OHLCV analysis refresh daily.
- Narrative analysis refreshes quarterly by default.
- Final synthesis refreshes daily.
- `force_refresh=True` bypasses these cached LLM and analysis outputs.

## 6. Tier 0: Numeric Engine

Tier 0 is implemented in `pipeline/tier0_numeric/__init__.py`.

Its job is to compute factual numeric evidence. It does not use an LLM.

The output schema is `Tier0Output` in `pipeline/schemas/tier0.py`.

### 6.1 Solvency and Liquidity

Implemented in `pipeline/tier0_numeric/ratios.py`.

It pulls financial statements from yfinance and computes balance-sheet health:

- current ratio
- quick ratio
- cash ratio
- operating cash flow ratio
- working capital
- debt/equity
- debt ratio
- equity ratio
- debt/capital
- interest coverage
- fixed-charge coverage
- cash-flow-to-debt
- 8-quarter current-ratio trend

This tells us whether the company can survive stress and meet obligations.

### 6.2 Efficiency

Implemented in `pipeline/tier0_numeric/efficiency.py`.

It estimates how efficiently the business uses operating assets:

- inventory turnover
- receivables turnover
- payables turnover
- DSO, or days sales outstanding

These are useful because margin strength is not enough if cash conversion is weak.

### 6.3 Profitability

Implemented in `pipeline/tier0_numeric/profitability.py`.

It computes:

- gross margin
- operating margin
- net margin
- ROA
- ROE
- ROCE
- EPS
- ROI

This captures how good the core business model is.

### 6.4 Investor Behavior

Implemented in `pipeline/tier0_numeric/investor_signals.py`.

It tries to collect insider transaction information through yfinance:

- insider buys over 90 days
- insider sells over 90 days
- short interest delta when available
- institutional delta field exists in the schema, though the current implementation is limited by available yfinance fields

This is a "smart money" proxy, not a complete institutional-flow engine.

### 6.5 Technicals

Implemented in `pipeline/tier0_numeric/technicals.py`.

It uses roughly five years of OHLCV data from yfinance and computes:

- RSI-14
- MACD signal
- annualized volatility
- rolling Sharpe distribution
- legacy 60-day Sharpe
- full-period max drawdown
- yearly drawdown map
- legacy 60-day max drawdown
- risk-free rate from FRED
- number of data days

This gives the first technical read, but it is still part of Tier 0 because it is purely mathematical.

### 6.6 Peer Dynamics

Implemented in `pipeline/tier0_numeric/peer_dynamics.py`.

The pipeline discovers peers using a curated fallback list for known NSE tickers and available yfinance metadata. It then compares the target ticker against peers for:

- relative Sharpe
- relative volatility
- relative drawdown
- Sharpe percentile rank
- volatility percentile rank
- peer count
- peer confidence

The peer system is conservative. If it cannot find reliable peers, it returns low peer confidence rather than forcing a comparison.

### 6.7 Normalized Metrics

Implemented in `pipeline/tier0_numeric/normalization.py`.

Raw metrics can be misleading across industries. A good current ratio for one sector may be average or weak in another.

The normalization module compares the ticker to peer medians:

- current ratio vs peers
- debt/equity vs peers
- gross margin vs peers
- ROE vs peers
- macro regime context

This lets the LLM reason with sector-aware deltas.

### 6.8 Factor Exposure

Implemented in `pipeline/tier0_numeric/factor_model.py`.

The pipeline downloads daily Fama-French factor returns and aligns them with the ticker's daily returns. It then runs an OLS regression:

```text
stock excess return =
  alpha
  + market_beta * market_factor
  + size_loading * size_factor
  + value_loading * value_factor
  + profitability_loading * profitability_factor
  + investment_loading * investment_factor
  + momentum_loading * momentum_factor
  + residual
```

The output includes:

- annualized alpha
- alpha t-statistic
- whether alpha is statistically significant
- factor loadings
- R-squared
- residual volatility

This tells us whether performance looks stock-specific or mostly explained by common factors.

### 6.9 Options Signals

Implemented in `pipeline/tier0_numeric/options_signals.py`.

It uses the yfinance options chain where available and computes forward-looking derivatives-market context:

- IV rank
- put/call ratio by volume
- put/call ratio by open interest
- put skew
- term structure
- at-the-money IV
- near-term event risk

Options data can be unavailable for many tickers, so this is non-critical.

### 6.10 Macro Regime

Implemented in `pipeline/tier0_numeric/macro_regime.py`.

It fetches FRED series and classifies:

- rate regime: accommodative, transitioning, tightening, or neutral
- credit regime: risk-on, risk-off, stress, or neutral
- volatility regime: low, moderate, or high
- composite macro label: bullish, neutral, or bearish

The macro context is passed to Tier 1A and Tier 2 so the same company metrics can be interpreted differently in different environments.

### 6.11 Data Quality

Tier 0 tracks:

- fields requested
- fields received
- missing fields
- warnings
- quality score

If both solvency and technicals are missing, the ticker is skipped because the pipeline has neither fundamental nor market evidence.

## 7. Tier 1A: Quant Synthesizer

Implemented in `pipeline/tier1_llm/quant_synthesizer.py`.

Tier 1A receives the structured `Tier0Output` for up to three tickers at a time. It builds a prompt containing separate sections:

- solvency and liquidity
- efficiency
- profitability
- investor behavior
- technicals
- normalized peer metrics
- factor decomposition
- macro context
- options signals
- data quality

Gemini is instructed to reason about each section independently and output `QuantSynthesizerOutput`.

The output includes:

- solvency read
- efficiency read
- profitability read
- smart-money read
- technical read
- macro fit
- factor exposure interpretation
- data quality score

Tier 1A does not produce the final buy/sell decision. It is a specialist analyst.

## 8. Tier 1B: Narrative Synthesizer

Implemented in `pipeline/tier1_llm/narrative_synthesizer.py`.

Tier 1B gathers qualitative context:

- recent news from Tavily
- earnings-call data from Finnhub or mock fallback

Before using the LLM, earnings calls are preprocessed:

- `segment.py` splits transcript text into speaker-level sections.
- `roles.py` normalizes speaker roles.
- `filter_qa_relevance` keeps the most relevant analyst Q&A.
- `sentiment_lexicon.py` computes finance-oriented sentiment.
- `extractive.py` extracts prepared-remarks sentences around financial keywords.

The point is to reduce noisy transcript text into structured evidence before the model reads it.

Gemini then returns `NarrativeSynthesizerOutput`:

- news tone
- key news drivers
- earnings tone
- guidance direction
- paraphrased key quotes
- management hedging flag
- analyst concerns
- outlook summary
- risk flags
- competitive-position read
- data quality score

Tier 1B is cached quarterly because earnings-call and narrative context generally changes slower than price.

## 9. Tier 1C: Raw OHLCV Analyzer and Moirai 1.1-R Forecaster

Implemented in `pipeline/tier1_llm/ohlcv_analyzer.py`.

Tier 1C analyzes raw yfinance OHLCV data directly. It has two parts:

- A deterministic market-structure analyzer for trend, volatility, drawdown, volume, and range position.
- A Moirai 1.1-R multivariate OHLCV forecasting path for probabilistic 5-day forward signals.

It does not call an LLM. Moirai is a time-series forecasting model, not a language model.

Moirai 1.1-R is used specifically because the referenced design needs multivariate OHLCV support. Moirai 2.0 is not used for this layer because it removed multivariate support.

### 9.1 Input

The input is a raw yfinance-style DataFrame:

```text
Date index
Open
High
Low
Close
Volume
```

The pipeline fetches about two years of OHLCV data through the vendor layer.

### 9.2 Preprocessing

Tier 1C:

- accepts standard or yfinance MultiIndex columns
- validates required OHLCV columns
- converts values to numeric
- sorts dates
- removes duplicate dates
- regularizes the data to a business-day calendar
- forward-fills holiday gaps
- fills missing open/high/low with close if needed
- clips volume at zero
- rejects empty or invalid close-price data

This lets the analyzer handle raw yfinance quirks safely.

### 9.3 Metrics

Tier 1C computes:

- latest close
- 5-day return
- 21-day return
- 63-day return
- 126-day return
- 252-day return
- annualized volatility
- downside volatility
- 20-day moving average
- 50-day moving average
- 200-day moving average
- moving-average alignment
- annualized log-slope trend
- trend direction
- trend strength
- drawdown from 52-week high
- price location inside 52-week range
- 63-day volume z-score
- volume trend: accumulating, distributing, neutral, or unavailable
- 14-day ATR as percent of close
- Moirai 1.1-R 5-day implied return
- Moirai implied volatility
- Moirai directional confidence
- Moirai regime uncertainty
- Moirai model/status fields
- regime label
- summary signals
- warnings
- data quality score

### 9.4 Output

The schema is `RawOHLCVAnalysis` in `pipeline/schemas/llm_schemas.py`.

Example fields:

```json
{
  "ticker": "MSFT",
  "trend_direction": "bearish",
  "trend_strength": 0.3723,
  "moving_average_alignment": "bearish",
  "volume_trend": "distributing",
  "moirai_status": "ok",
  "moirai_model": "Salesforce/moirai-1.1-R-small",
  "moirai_implied_return_5d": 0.0618,
  "moirai_implied_volatility": 0.0407,
  "moirai_directional_confidence": 0.95,
  "moirai_regime_uncertainty": 0.0378,
  "drawdown_from_52w_high": -0.3076,
  "price_location_52w": 0.1084,
  "regime_label": "trend_down_low_vol",
  "summary_signals": [
    "bearish_price_trend",
    "bearish_moving_average_stack",
    "volume_distributing",
    "deep_drawdown_from_52w_high",
    "near_52w_low"
  ],
  "data_quality_score": 1.0
}
```

Tier 1C is cached daily with key:

```text
{ticker}:{today}:ohlcv_v1
```

### 9.5 Why Tier 1C Matters

Tier 1C gives Tier 2 more tactical evidence:

- Is the stock above or below key moving averages?
- Is price near a 52-week high or low?
- Is volume confirming the move?
- Is the move high-volatility or low-volatility?
- Is the stock in a drawdown that conflicts with otherwise good fundamentals?
- Does Moirai's forecast distribution imply positive or negative 5-day return?
- How uncertain is the forecast distribution?
- What percent of Moirai samples are bullish?

That is exactly the kind of evidence needed for the 30-day tactical signal.

## 10. Tier 2: General Expert

Implemented in `pipeline/tier2_llm/general_expert.py`.

Tier 2 receives:

- Tier 1A quantitative report
- Tier 1B narrative report
- Tier 1C raw OHLCV report
- macro regime context
- consistency flags

Its job is to merge specialist reports into final signals.

The output schema is `GeneralExpertOutput`:

- ticker
- tactical 30-day signal
- structural 1-year signal
- overall confidence
- rationale
- conflicting signals
- data quality score
- macro adjustment
- consistency flags

The final signal is split into two horizons because short-term and long-term evidence can conflict. For example:

- A company can be structurally strong but tactically weak if price momentum is breaking down.
- A company can be tactically bullish but structurally weak if a short squeeze or news event lifts price temporarily.

Tier 2 is instructed to name these conflicts instead of averaging them away.

## 11. Consistency Checking

Implemented in `pipeline/infra/consistency_checker.py`.

After Tier 1A, the pipeline checks whether LLM interpretations contradict Tier 0 numbers. For example, if the LLM calls solvency strong while the current ratio and debt metrics are weak, that can be flagged.

After Tier 2, the pipeline also checks the final output against upstream Tier 1A and Tier 1B reports.

These flags are appended to the final result so downstream consumers can see where the model may need human review.

## 12. API Layer

Implemented in `pipeline/api.py`.

The FastAPI service exposes:

- `GET /health`: service status and configured provider flags.
- `GET /v1/config`: pipeline modes and environment configuration.
- `POST /v1/pipeline/run`: full orchestrated pipeline for tickers.
- `GET /v1/fundamentals/{ticker}`: deterministic fundamental report generated from Tier 0.
- `GET /v1/fundamentals/{ticker}/data`: raw Tier 0 source data for API inspection.
- `GET /v1/news/{ticker}`: Tavily news payload.
- `GET /v1/earnings/{ticker}/important-parts`: preprocessed earnings-call output.
- `GET /v1/tickers/{ticker}/context`: combined news and earnings-call context.

The API has two kinds of outputs:

- Full MoE pipeline output from `/v1/pipeline/run`.
- A deterministic Tier-0-based fundamental report from `/v1/fundamentals/{ticker}`.

## 13. Frontend Data

The repo also contains a Next.js frontend under `frontend/`.

The frontend has:

- dashboard page
- portfolio page
- profile/auth components
- local market data helper script
- Supabase client helpers and SQL models

The frontend is separate from the core pipeline. It can call the API endpoints or use its own local/public data files depending on the route.

## 14. Error Handling Philosophy

The pipeline intentionally avoids silent corruption.

Important rules:

- Missing numeric data becomes `None`, not `0.0`.
- Non-critical modules can fail without killing the whole ticker.
- Critical failure occurs when both core fundamental and technical evidence are unavailable.
- Data quality scores travel with the output.
- LLM prompts are told to reduce confidence when data is missing.
- Cache and vendor failures are logged.
- Run summaries track skipped, failed, and successful tickers.

This is important in finance because false precision is worse than uncertainty.

## 15. How a Full Run Works

Suppose the user runs:

```bash
python main.py --tickers AAPL,MSFT
```

The process is:

1. The orchestrator starts a run tracker.
2. For each ticker, Tier 0 pulls yfinance financials and OHLCV.
3. Tier 0 computes solvency, profitability, efficiency, technicals, peer dynamics, factor exposure, options signals, and macro context.
4. If Tier 0 has enough evidence, the ticker continues.
5. Tier 1A checks the daily quant cache.
6. If not cached, Tier 1A sends structured numeric evidence to Gemini and stores the result.
7. Tier 1B checks the quarterly narrative cache.
8. If not cached, it gathers news, preprocesses earnings-call text, asks Gemini for narrative interpretation, and stores the result.
9. Tier 1C checks the daily OHLCV cache.
10. If not cached, it fetches raw OHLCV, analyzes market structure, and stores the result.
11. Tier 2 checks the daily final-output cache.
12. If not cached, it sends Tier 1A, Tier 1B, Tier 1C, macro context, and consistency flags to Gemini.
13. Tier 2 returns tactical and structural signals.
14. The run tracker records duration, cache hits, failures, and semantic inconsistencies.
15. The final response includes ticker outputs plus `_run_summary`.

## 16. What Makes This a Pipeline Instead of One Big Prompt

A one-shot LLM prompt would be fragile because it would mix:

- raw prices
- financial statements
- news
- earnings transcript
- macro conditions
- peer comparison
- final investment decision

That creates too much room for hallucination and untraceable reasoning.

This pipeline splits the work:

- Tier 0: calculate facts.
- Tier 1A: interpret numeric facts.
- Tier 1B: interpret narrative facts.
- Tier 1C: interpret raw market-structure data and add Moirai 1.1-R probabilistic OHLCV forecasts.
- Tier 2: merge independent analyst views.

The result is more explainable, testable, and debuggable.

## 17. Current Limitations

The current implementation is useful, but it has limitations:

- yfinance can have missing or delayed fields.
- Peer discovery is still conservative and fallback-heavy.
- Finnhub transcripts require an API key; otherwise the mock transcript is used.
- Tavily news requires `TAVILY_API_KEY`; otherwise news is explicitly unavailable.
- FRED calls use `DEMO_KEY`, which is fine for low-volume use but not production.
- Options data is not available for every ticker.
- Tier 1A, Tier 1B, and Tier 2 depend on `GEMINI_API_KEY`.
- Tier 1C now uses Moirai 1.1-R when dependencies and Hugging Face weights are available; if not, it still returns deterministic diagnostics and marks `moirai_status` as `unavailable` or `failed`.
- The API's `/v1/fundamentals/{ticker}` route currently builds a deterministic Tier-0 report, not the full Tier 1/Tier 2 MoE output.

## 18. Testing and Verification

Current tests for the newly added Tier 1C live in `tests/test_ohlcv_analyzer.py`.

They verify:

- raw yfinance-style MultiIndex columns are cleaned correctly
- bullish synthetic OHLCV data produces a bullish structure
- invalid frames are skipped without breaking the batch

The Tier 1C analyzer was also manually checked with live yfinance data. After installing the Moirai 1.1-compatible stack, `AAPL` returned `moirai_status="ok"` with populated 5-day implied return, implied volatility, directional confidence, and regime uncertainty fields.

Run tests with:

```bash
python -m unittest discover
```

## 19. Required Environment Variables

Minimum useful setup:

```text
GEMINI_API_KEY=...
```

Optional enrichments:

```text
TAVILY_API_KEY=...
FINNHUB_API_KEY=...
DATABASE_URL=...
```

If optional keys are missing, the pipeline falls back where possible and marks missing context explicitly.

## 20. Short Summary

This pipeline is an explainable stock-analysis system.

It uses yfinance as the main raw financial and OHLCV dataset, enriches it with FRED macro data, Kenneth French factor data, Tavily news, and Finnhub or mock earnings transcripts. It computes numeric evidence in Python, asks Gemini to interpret structured quant and narrative evidence, adds Tier 1C raw OHLCV market-structure diagnostics plus Moirai 1.1-R forecasts, and then merges everything into final tactical and structural investment signals.
