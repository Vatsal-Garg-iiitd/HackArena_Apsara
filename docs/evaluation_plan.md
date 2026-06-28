# Evaluation Plan for HackArena Pipeline

## 1. Goal

The goal is to evaluate whether the pipeline produces accurate, grounded, useful stock analysis.

We should not evaluate the whole system with one vague "accuracy" number. The pipeline has multiple tiers, and each tier has a different responsibility:

- Tier 1A interprets numeric financial and market metrics.
- Tier 1B interprets narrative evidence from news and earnings calls.
- Tier 2 combines the specialist reports into final tactical and structural signals.

So the evaluation must measure:

- schema correctness
- factual grounding
- agreement with human labels
- consistency with upstream data
- financial usefulness of final signals
- calibration of confidence scores
- robustness when data is missing or noisy
- latency and cost

## 2. Core Principle

Accuracy requires labels.

Without labeled examples, we can only test formatting, consistency, and plausibility. To measure real accuracy, we need a benchmark dataset containing:

- ticker
- date of analysis
- Tier 0 numeric data as of that date
- news and earnings-call evidence available as of that date
- human labels for Tier 1A and Tier 1B outputs
- future price outcomes for Tier 2 tactical and structural signals

The most important rule is no lookahead bias. When evaluating a prediction made on `2025-01-15`, the model can only use data available on or before `2025-01-15`.

## 3. Evaluation Dataset

Create a benchmark table with one row per ticker-date.

Recommended initial dataset:

- 50 to 100 liquid tickers.
- 8 to 12 evaluation dates per ticker.
- Mix of US and Indian tickers if both are supported.
- Include bull, bear, sideways, high-volatility, and earnings-event periods.
- Include examples with missing news, missing options data, and weak yfinance fields.

Each row should include:

```json
{
  "ticker": "AAPL",
  "as_of_date": "2025-03-31",
  "tier0_snapshot": {},
  "news_snapshot": [],
  "earnings_snapshot": {},
  "tier1a_gold": {},
  "tier1b_gold": {},
  "tier2_gold": {},
  "future_returns": {
    "return_30d": 0.042,
    "return_1y": 0.181,
    "benchmark_return_30d": 0.018,
    "benchmark_return_1y": 0.102
  }
}
```

## 4. Tier 1A Evaluation: Quant Synthesizer

Tier 1A receives Tier 0 numeric data and produces a structured quant interpretation. It should be evaluated against human labels and against the source metrics.

### 4.1 Fields to Evaluate

Tier 1A output fields:

- `solvency_read.trend`
- `efficiency_read.trend`
- `profitability_read.strength`
- `smart_money_read.signal`
- `technical_read.signal`
- `macro_fit`
- `factor_exposure_read`
- `data_quality_score`

### 4.2 Classification Accuracy

For categorical fields, use:

- accuracy
- macro F1
- precision per class
- recall per class
- confusion matrix

Example:

```text
solvency_read.trend:
  labels: improving, stable, deteriorating
  metrics: accuracy, macro_f1, confusion_matrix
```

Macro F1 matters because classes may be imbalanced. For example, most companies may be labeled `stable`, so raw accuracy can look good even if the model misses every `deteriorating` case.

### 4.3 Numeric Consistency Score

Tier 1A must not contradict Tier 0.

Create deterministic rules:

- If `current_ratio < 1.0` and `debt_equity > 2.0`, solvency should usually not be labeled `improving` unless the rationale explains a strong offset.
- If `rsi_14 > 70`, technical read should usually mention overbought risk.
- If `macd_signal == bearish`, technical read should not be strongly bullish without explanation.
- If `gross_margin_vs_peers < 0` and `roe_vs_peers < 0`, profitability should not be labeled strongly positive without explanation.
- If `alpha_significant == False`, factor read should not claim statistically significant alpha.

Metric:

```text
numeric_consistency_rate =
  1 - (number_of_rule_violations / number_of_applicable_rules)
```

Target:

- MVP: `>= 0.90`
- Strong: `>= 0.95`

### 4.4 Rationale Grounding

The rationale should cite actual input fields.

Metrics:

- evidence citation rate: percent of rationales that reference at least one relevant Tier 0 metric.
- unsupported claim rate: percent of rationales containing claims not supported by Tier 0.
- contradiction rate: percent of rationales that contradict the chosen label.

Evaluation can be done by human review initially, then later with an LLM-as-judge rubric.

### 4.5 Confidence Calibration

Tier 1A outputs confidence scores. Confidence should mean "probability this label is correct."

Metrics:

- Brier score for each classification field.
- Expected Calibration Error, or ECE.
- accuracy by confidence bucket:
  - 0.0 to 0.5
  - 0.5 to 0.7
  - 0.7 to 0.85
  - 0.85 to 1.0

Good behavior:

- 80% confidence predictions should be correct about 80% of the time.
- Low-quality data should lower confidence.

### 4.6 Data Quality Sensitivity

Tier 1A should react correctly when fields are missing.

Test cases:

- solvency missing
- technicals missing
- factor exposure missing
- options signals missing
- peer comparison missing

Metrics:

- missing-data acknowledgement rate
- confidence penalty rate
- hallucinated-data rate

Target:

- hallucinated-data rate should be near zero.

## 5. Tier 1B Evaluation: Narrative Synthesizer

Tier 1B receives recent news and preprocessed earnings-call data. It outputs qualitative labels and explanations.

### 5.1 Fields to Evaluate

Tier 1B output fields:

- `news_sentiment.tone`
- `news_sentiment.key_drivers`
- `earnings_read.tone`
- `earnings_read.guidance_direction`
- `earnings_read.management_hedging_detected`
- `earnings_read.analyst_concerns`
- `outlook.summary`
- `outlook.risk_flags`
- `outlook.new_risks_vs_prior`
- `competitive_position.relative_strength`
- `data_quality_score`

### 5.2 Human-Labeled Narrative Accuracy

Build labels from analyst review.

For each ticker-date, human annotators should label:

- news tone: positive, negative, mixed, neutral
- earnings tone: positive, negative, mixed, neutral
- guidance direction: raised, maintained, lowered, none_given
- management hedging: true or false
- key risks
- competitive position: gaining, losing, stable

Metrics:

- accuracy
- macro F1
- confusion matrix
- per-class precision and recall

### 5.3 Key Driver Recall and Precision

Tier 1B must identify the right reasons, not just the right sentiment.

For key drivers, analyst concerns, and risk flags:

```text
driver_precision = correct_model_drivers / all_model_drivers
driver_recall = correct_model_drivers / gold_drivers
driver_f1 = 2 * precision * recall / (precision + recall)
```

Example gold drivers:

- margin expansion
- revenue deceleration
- guidance raise
- regulatory risk
- demand weakness
- FX headwind
- debt refinancing risk

### 5.4 Source Grounding

Narrative outputs must be grounded in the supplied news and earnings text.

Metrics:

- supported claim rate
- unsupported claim rate
- quote/paraphrase faithfulness
- source coverage rate

Human rubric:

```text
2 = fully supported by supplied evidence
1 = partially supported or too vague
0 = unsupported or contradicted
```

### 5.5 Earnings Call Specific Metrics

For earnings calls:

- guidance direction accuracy
- management hedging detection F1
- analyst concern recall
- prepared remarks vs Q&A tone-shift detection
- financial sentiment agreement with human label

The Q&A section is important because management often sounds positive in prepared remarks, while analyst questions reveal pressure points.

### 5.6 News Freshness and Relevance

Tier 1B depends on retrieval quality from Tavily.

Measure:

- percent of news items published within required time window
- percent of news items actually related to the ticker
- duplicate article rate
- irrelevant article rate
- source quality score

This separates model failure from retrieval failure.

### 5.7 Missing Context Behavior

When `TAVILY_API_KEY` or `FINNHUB_API_KEY` is missing, Tier 1B should say data is unavailable and lower confidence.

Metrics:

- missing-source acknowledgement rate
- hallucinated-news rate
- hallucinated-earnings-call rate
- confidence penalty rate

Target:

- hallucinated-news and hallucinated-transcript rate should be zero.

## 6. Tier 2 Evaluation: Final Signal

Tier 2 is evaluated differently because it produces an investment signal. It should be judged both as a reasoning system and as a signal generator.

### 6.1 Fields to Evaluate

Tier 2 output fields:

- `signals.tactical_horizon_30d.direction`
- `signals.tactical_horizon_30d.confidence`
- `signals.tactical_horizon_30d.corroborating_signals`
- `signals.tactical_horizon_30d.contradicting_signals`
- `signals.structural_horizon_1y.direction`
- `signals.structural_horizon_1y.confidence`
- `signals.structural_horizon_1y.corroborating_signals`
- `signals.structural_horizon_1y.contradicting_signals`
- `overall_confidence`
- `rationale`
- `conflicting_signals`
- `macro_regime_adjustment`
- `consistency_flags`

### 6.2 Directional Accuracy

Convert future returns into labels.

For 30-day tactical signal:

```text
if excess_return_30d >= +3%: bullish
if excess_return_30d <= -3%: bearish
else: neutral
```

For 1-year structural signal:

```text
if excess_return_1y >= +8%: bullish
if excess_return_1y <= -8%: bearish
else: neutral
```

Excess return means stock return minus benchmark return.

Benchmarks:

- US stocks: SPY or sector ETF.
- Indian stocks: NIFTY 50, NIFTY sector index, or a broad India ETF.

Metrics:

- accuracy
- macro F1
- balanced accuracy
- confusion matrix
- bullish precision
- bearish precision
- neutral accuracy

### 6.3 Financial Performance Metrics

Backtest the final signals.

Map directions to positions:

```text
bullish = +1
neutral = 0
bearish = -1 or 0, depending on whether shorting is allowed
```

Metrics:

- average forward return by signal class
- hit rate
- long-only hit rate
- short hit rate, if shorting is allowed
- annualized return
- annualized volatility
- Sharpe ratio
- Sortino ratio
- max drawdown
- Calmar ratio
- turnover
- transaction-cost-adjusted return
- benchmark-relative alpha
- information ratio

Important grouped metrics:

- 30-day tactical performance
- 1-year structural performance
- high-confidence-only performance
- low-confidence performance
- sector-level performance
- market-regime-level performance

### 6.4 Confidence-Weighted Evaluation

Tier 2 confidence should predict correctness and magnitude.

Metrics:

- Brier score
- Expected Calibration Error
- accuracy by confidence bucket
- average return by confidence bucket
- Sharpe by confidence bucket

Good behavior:

- High-confidence bullish calls should outperform low-confidence bullish calls.
- Low-confidence calls should be closer to random.
- Bearish high-confidence calls should avoid or identify underperformers.

### 6.5 Conflict Resolution Accuracy

Tier 2 must handle conflicts between tiers.

Examples:

- Tier 1A fundamentals bullish, Tier 1C price trend bearish.
- Tier 1B narrative negative, Tier 1A solvency strong.
- Macro regime bearish, company-specific signals bullish.

Metrics:

- conflict detection rate
- conflict explanation quality
- correct horizon separation rate
- contradiction omission rate

Human rubric:

```text
2 = conflict identified and resolved with correct horizon logic
1 = conflict mentioned but weakly resolved
0 = conflict ignored or resolved incorrectly
```

### 6.6 Grounding in Upstream Reports

Tier 2 should not invent new facts.

Metrics:

- upstream evidence citation rate
- unsupported claim rate
- contradiction with Tier 1A rate
- contradiction with Tier 1B rate
- contradiction with Tier 1C rate
- consistency-check violation rate

Target:

- unsupported claim rate should be below 5% in MVP.

### 6.7 Macro Adjustment Evaluation

When macro regime is bearish, bullish tactical calls should require stronger company-specific evidence.

Metrics:

- macro context usage rate
- macro adjustment correctness
- bullish-confidence penalty rate in bearish macro regimes
- bearish-confidence penalty rate in bullish macro regimes

This can be evaluated by human labels initially.

## 7. End-to-End Evaluation

End-to-end evaluation asks: did the final pipeline produce useful, reliable signals?

### 7.1 Offline Backtest

For each ticker-date:

1. Freeze all input data as of that date.
2. Run the full pipeline.
3. Store Tier 1A, Tier 1B, Tier 1C, and Tier 2 outputs.
4. Wait or use historical future returns to score outcomes.
5. Compare against benchmark returns.

Metrics:

- tactical 30-day directional accuracy
- structural 1-year directional accuracy
- average excess return by signal
- high-confidence signal excess return
- Sharpe ratio
- max drawdown
- hit rate
- turnover
- transaction-cost-adjusted return

### 7.2 Ablation Tests

Run the pipeline with pieces removed:

- Tier 1A only
- Tier 1B only
- Tier 1C only
- Tier 1A + Tier 1B
- Tier 1A + Tier 1C
- Tier 1A + Tier 1B + Tier 1C

Measure whether adding Tier 1C improves:

- tactical 30-day accuracy
- high-confidence signal Sharpe
- drawdown avoidance
- conflict detection

This proves whether each tier actually adds value.

### 7.3 Robustness Tests

Stress-test with:

- missing OHLCV
- missing news
- missing transcript
- missing options chain
- stale financial statements
- extreme volatility periods
- earnings gap days
- low-liquidity tickers
- ticker symbols with suffixes like `.NS`

Metrics:

- graceful failure rate
- false confidence rate
- crash rate
- data quality propagation rate

## 8. LLM-as-Judge Rubrics

Human labels are best, but expensive. For scalable review, use LLM-as-judge only for qualitative rubrics, not future-return truth.

Use it for:

- rationale grounding
- unsupported claims
- conflict explanation quality
- source faithfulness
- clarity of final rationale

Do not use it as the only judge for final investment accuracy.

Suggested rubric dimensions:

```text
grounding:
  2 = all claims supported by supplied evidence
  1 = mostly supported, minor vague claims
  0 = unsupported or hallucinated claims

conflict_handling:
  2 = identifies and resolves conflicts by horizon
  1 = mentions conflict but weak explanation
  0 = ignores major conflict

financial_reasoning:
  2 = correct financial interpretation
  1 = partially correct but shallow
  0 = incorrect interpretation

data_quality_awareness:
  2 = explicitly adjusts confidence for missing/weak data
  1 = mentions missing data but weak adjustment
  0 = ignores missing data
```

## 9. Recommended Acceptance Targets

Initial MVP targets:

```text
Tier 1A:
  schema_valid_rate >= 99%
  numeric_consistency_rate >= 90%
  macro_f1 >= 0.65 for human-labeled categories
  unsupported_claim_rate <= 10%

Tier 1B:
  schema_valid_rate >= 99%
  tone_macro_f1 >= 0.65
  guidance_direction_accuracy >= 75%
  key_driver_f1 >= 0.60
  hallucinated_source_rate <= 5%

Tier 2:
  schema_valid_rate >= 99%
  tactical_directional_accuracy > benchmark baseline
  structural_directional_accuracy > benchmark baseline
  high_confidence_signals outperform low_confidence_signals
  unsupported_claim_rate <= 5%
  conflict_detection_rate >= 80%
```

Strong targets:

```text
Tier 1A:
  numeric_consistency_rate >= 95%
  macro_f1 >= 0.75
  calibrated confidence with ECE <= 0.10

Tier 1B:
  tone_macro_f1 >= 0.75
  key_driver_f1 >= 0.70
  hallucinated_source_rate <= 2%

Tier 2:
  positive excess return for bullish high-confidence calls
  negative or below-benchmark return for bearish high-confidence calls
  Sharpe ratio above benchmark after transaction costs
  ECE <= 0.10
```

## 10. Evaluation Implementation Plan

### Phase 1: Logging and Storage

Store every pipeline run with:

- input ticker
- as-of date
- Tier 0 snapshot
- news snapshot
- earnings snapshot
- Tier 1A output
- Tier 1B output
- Tier 1C output
- Tier 2 output
- model name
- prompt version
- latency
- token usage if available
- cache status

This gives us the raw material for evaluation.

### Phase 2: Build Gold Label Dataset

Create a manually labeled file:

```text
eval/gold_labels.csv
```

Columns:

- ticker
- as_of_date
- solvency_label
- profitability_label
- technical_label
- news_tone_label
- earnings_tone_label
- guidance_label
- competitive_position_label
- tactical_gold_label
- structural_gold_label
- notes

Start with 100 to 200 examples.

### Phase 3: Add Deterministic Validators

Create validators for:

- schema validity
- required fields
- confidence range
- numeric consistency
- missing-data acknowledgement
- unsupported claims based on simple string/entity checks

These run without humans.

### Phase 4: Add Forward Return Scoring

For every ticker-date, fetch future OHLCV and compute:

- 30-day return
- 1-year return
- benchmark-relative return
- volatility during holding window
- max drawdown during holding window

Then score Tier 2 signals against realized outcomes.

### Phase 5: Run Ablations

Run and compare:

- no Tier 1C
- with Tier 1C
- no Tier 1B
- Tier 1A only
- full pipeline

This reveals which modules actually improve performance.

### Phase 6: Calibration Analysis

Bucket predictions by confidence and compare predicted confidence to realized correctness.

Output:

- calibration table
- reliability diagram
- Brier score
- ECE

### Phase 7: Regression Dashboard

Create a recurring report:

- Tier 1A accuracy and consistency
- Tier 1B narrative accuracy
- Tier 2 signal performance
- latency and cost
- top failure cases
- examples of hallucination or contradiction
- improvement or regression vs previous prompt/model version

## 11. Minimum Viable Evaluation Script

The first evaluation script should do five things:

1. Load saved pipeline outputs.
2. Validate schemas.
3. Run consistency rules.
4. Join future price outcomes.
5. Produce a metrics JSON report.

Example output:

```json
{
  "tier1a": {
    "schema_valid_rate": 1.0,
    "numeric_consistency_rate": 0.93,
    "avg_confidence": 0.71
  },
  "tier1b": {
    "schema_valid_rate": 1.0,
    "source_grounding_score": 0.82,
    "missing_context_ack_rate": 0.96
  },
  "tier2": {
    "tactical_accuracy": 0.57,
    "structural_accuracy": 0.61,
    "bullish_30d_avg_excess_return": 0.018,
    "high_confidence_hit_rate": 0.64,
    "unsupported_claim_rate": 0.04
  }
}
```

## 12. Most Important Metrics to Track First

If we only track a small set at the start, track these:

Tier 1A:

- schema valid rate
- numeric consistency rate
- human-label macro F1
- confidence calibration

Tier 1B:

- tone macro F1
- guidance direction accuracy
- key driver F1
- hallucinated source rate

Tier 2:

- 30-day excess return by tactical signal
- 1-year excess return by structural signal
- high-confidence hit rate
- Sharpe of signal-following strategy
- conflict detection rate
- unsupported claim rate

These metrics tell us whether the pipeline is correct, grounded, and financially useful.

