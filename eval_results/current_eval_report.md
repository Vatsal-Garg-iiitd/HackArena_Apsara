# HackArena Evaluation Results

## Run Metadata

- Evaluation date: `2026-06-28`
- Evaluated tickers: `AAPL`, `MSFT`
- Sample size: `2`
- Metrics JSON: `eval_results/current_eval_metrics.json`
- Live full-pipeline command attempted: `python main.py --tickers AAPL,MSFT`

## Execution Status

The evaluation was partially executed end to end.

Tier 0, Tier 1A, Tier 1B, and Tier 1C artifacts were available for both tickers. A full current Tier 2 run could not complete because the Gemini API returned a quota error:

```text
429 RESOURCE_EXHAUSTED
Quota exceeded for gemini-2.5-flash free-tier requests.
```

Because of that, current `general_v3` Tier 2 outputs were not available. Tier 2 scoring below uses the latest cached `general_v2` outputs where available:

- `AAPL`: `AAPL:2026-06-28:general_v2`
- `MSFT`: `MSFT:2026-06-27:general_v2`

Important: these cached Tier 2 outputs are legacy outputs and are not Tier 1C-aware. They are useful for checking schema and basic consistency, but they are not a complete evaluation of the newest Tier 2 prompt that includes Tier 1C raw OHLCV analysis.

## Summary Scores

| Metric | Score | What It Infers |
|---|---:|---|
| Tier 1A schema valid rate | `1.00` | All evaluated Tier 1A outputs matched the expected Pydantic schema. The model returned parseable structured quant analysis. |
| Tier 1B schema valid rate | `1.00` | All evaluated Tier 1B outputs matched the expected narrative schema. The model returned parseable structured qualitative analysis. |
| Tier 1C schema valid rate | `1.00` | All raw OHLCV analyzer outputs matched the expected schema. Note: this report was generated before Moirai fields were successfully installed and smoke-tested locally. |
| Tier 2 schema valid rate | `1.00` | Cached legacy Tier 2 outputs matched the expected final-signal schema. This does not prove current `general_v3` works because quota blocked it. |
| Tier 1A numeric consistency proxy | `1.00` | No Tier 1A outputs violated the current deterministic consistency rules against Tier 0 numeric data. |
| Tier 1A average consistency multiplier | `1.00` | No confidence penalty was applied by the consistency checker. |
| Tier 1A average confidence | `0.8072` | Tier 1A was generally confident in its quant classifications. This is calibration only after we compare against human labels. |
| Tier 1B average confidence | `0.5687` | Tier 1B was materially less confident, which is reasonable because news and transcript context is noisier and Finnhub is not configured. |
| Tier 1C average data quality | `1.00` | Both raw OHLCV datasets were complete enough for clean analysis. |
| Tier 2 average confidence, legacy | `0.7375` | Cached final outputs were moderately/highly confident. This is not validated accuracy without future-return scoring. |
| Tier 2 simple conflict score, legacy | `1.00` | The cached Tier 2 outputs did not trigger the simple upstream-conflict rules used in this evaluation. |

## Per-Ticker Results

### AAPL

| Area | Result |
|---|---|
| Tier 1A cache key | `AAPL:2026-06-28:quant_v2` |
| Tier 1B cache key | `AAPL:2026Q2:narrative_v2` |
| Tier 1C cache key | `AAPL:2026-06-28:ohlcv_v1` |
| Tier 2 cache key | `AAPL:2026-06-28:general_v2` |
| Tier 1A average confidence | `0.7714` |
| Tier 1A consistency multiplier | `1.00` |
| Tier 1A inconsistency count | `0` |
| Tier 1A solvency read | `improving` |
| Tier 1A profitability read | `strong` |
| Tier 1A technical read | `neutral` |
| Tier 1A macro fit | `neutral` |
| Tier 1B average confidence | `0.6625` |
| Tier 1B news tone | `mixed` |
| Tier 1B earnings tone | `neutral` |
| Tier 1B guidance direction | `none_given` |
| Tier 1B competitive position | `gaining` |
| Tier 1B risk flag count | `4` |
| Tier 1C data quality | `1.00` |
| Tier 1C trend direction | `bullish` |
| Tier 1C trend strength | `0.2355` |
| Tier 1C volume trend | `distributing` |
| Tier 1C regime label | `trend_up_low_vol` |
| Tier 2 tactical direction, legacy | `neutral` |
| Tier 2 structural direction, legacy | `bullish` |
| Tier 2 average confidence, legacy | `0.7250` |
| Tier 2 Tier1C-aware? | `false` |

Inference:

- Tier 1A is internally consistent with Tier 0 for AAPL.
- Tier 1B is cautious: mixed news, neutral earnings tone, but gaining competitive position.
- Tier 1C shows a mild bullish price trend but distributing volume, so short-term evidence is not one-directional.
- Cached Tier 2 gave a neutral tactical call and bullish structural call, which is directionally sensible given mixed tactical evidence but strong structural/quant reads.
- This is not verified predictive accuracy yet because no future 30-day or 1-year outcome is available in the benchmark.

### MSFT

| Area | Result |
|---|---|
| Tier 1A cache key | `MSFT:2026-06-28:quant_v2` |
| Tier 1B cache key | `MSFT:2026Q2:narrative_v2` |
| Tier 1C cache key | `MSFT:2026-06-28:ohlcv_v1` |
| Tier 2 cache key | `MSFT:2026-06-27:general_v2` |
| Tier 1A average confidence | `0.8429` |
| Tier 1A consistency multiplier | `1.00` |
| Tier 1A inconsistency count | `0` |
| Tier 1A solvency read | `deteriorating` |
| Tier 1A profitability read | `strong` |
| Tier 1A technical read | `oversold` |
| Tier 1A macro fit | `neutral` |
| Tier 1B average confidence | `0.4750` |
| Tier 1B news tone | `mixed` |
| Tier 1B earnings tone | `neutral` |
| Tier 1B guidance direction | `none_given` |
| Tier 1B competitive position | `gaining` |
| Tier 1B risk flag count | `3` |
| Tier 1C data quality | `1.00` |
| Tier 1C trend direction | `bearish` |
| Tier 1C trend strength | `0.3808` |
| Tier 1C volume trend | `distributing` |
| Tier 1C regime label | `trend_down_low_vol` |
| Tier 2 tactical direction, legacy | `neutral` |
| Tier 2 structural direction, legacy | `bullish` |
| Tier 2 average confidence, legacy | `0.7500` |
| Tier 2 Tier1C-aware? | `false` |

Inference:

- Tier 1A is internally consistent with Tier 0 for MSFT.
- Tier 1A identifies a mixed structural picture: deteriorating solvency but strong profitability.
- Tier 1C is clearly tactically bearish: bearish trend, distributing volume, and low-volatility downtrend regime.
- Cached Tier 2 gives neutral tactical and bullish structural. The neutral tactical call is plausible, but because this cached output is not Tier1C-aware, it may underweight the new raw OHLCV bearish evidence.
- This ticker is a good candidate for re-running current `general_v3` once Gemini quota is available.

## What These Scores Do and Do Not Prove

### Proven By This Evaluation

The current run supports these conclusions:

1. Tier 1A, Tier 1B, Tier 1C, and cached Tier 2 outputs are schema-valid for the evaluated sample.
2. Tier 1A did not contradict Tier 0 according to the current deterministic consistency rules.
3. Tier 1C is producing clean OHLCV market-structure data for both tickers. After this report was generated, Tier 1C was updated and smoke-tested with Moirai 1.1-R as well.
4. The cached Tier 2 outputs do not trigger simple conflict checks against upstream Tier 1A/Tier 1B/Tier 1C evidence.
5. Tier 1B confidence is lower than Tier 1A confidence, which is directionally reasonable because the narrative layer is using noisier text evidence and no Finnhub transcript key is configured.

### Not Proven Yet

This evaluation does not yet prove:

1. True classification accuracy for Tier 1A.
2. True narrative accuracy for Tier 1B.
3. True predictive accuracy for Tier 2.
4. Sharpe ratio, hit rate, realized alpha, drawdown, or return performance.
5. Calibration of confidence scores against actual correctness.

Those require either human-labeled gold data or future realized return data.

## Missing Accuracy Metrics

| Planned Metric | Status | Why It Is Missing |
|---|---|---|
| Tier 1A macro F1 | Not measured | No human gold labels for solvency/profitability/technical classifications. |
| Tier 1B tone F1 | Not measured | No human gold labels for news tone, earnings tone, guidance, or risks. |
| Tier 1B key-driver F1 | Not measured | No annotated key-driver set for the news and earnings evidence. |
| Tier 2 30-day directional accuracy | Not measured | Current as-of date has no future 30-day realized return yet. |
| Tier 2 1-year directional accuracy | Not measured | Current as-of date has no future 1-year realized return yet. |
| Tier 2 Sharpe / alpha / drawdown | Not measured | Requires a historical backtest dataset and multiple dated predictions. |
| Confidence calibration | Not measured | Requires enough predictions with known correctness outcomes. |

## Operational Issues Found

### Gemini Quota Blocked Current Tier 2

The live run exhausted the Gemini free-tier request quota during Tier 2. This prevented current `general_v3` outputs from being generated for both tickers.

Impact:

- Tier 1A and Tier 1B can be evaluated from cache.
- Tier 1C can be evaluated directly.
- Current Tier 2 with Tier 1C cannot be fully evaluated until quota is available.

### SQLite OHLCV Cache Warning

During concurrent OHLCV writes, SQLite emitted:

```text
cannot commit - no transaction is active
```

Impact:

- Tier 0 still completed for both tickers.
- The warning suggests the SQLite fallback cache can be fragile under concurrent writes.
- For reliable batch evaluation, use PostgreSQL with a valid `DATABASE_URL` or serialize OHLCV cache writes.

### PostgreSQL Config Is Present But Not Usable

The environment has `DATABASE_URL`, but connection failed:

```text
PostgreSQL connection failed: fe_sendauth: no password supplied
```

Impact:

- The pipeline fell back to SQLite.
- Larger evaluation runs should fix PostgreSQL auth first.

## Overall Interpretation

Current scorecard:

```text
Schema reliability: strong
Tier 1A numeric consistency: strong
Tier 1B confidence: cautious / moderate
Tier 1C data quality: strong; Moirai 1.1-R now wired and smoke-tested separately
Tier 2 current-model evaluation: blocked by quota
True predictive accuracy: not yet measured
```

The best honest interpretation is:

The pipeline is structurally healthy on this small live sample. Outputs are valid, Tier 1A is not contradicting numeric inputs, and Tier 1C is producing clean market-structure signals. However, we cannot yet claim model accuracy in the statistical sense. To claim accuracy, we need a labeled evaluation dataset and historical forward-return scoring.

## Next Steps To Complete Accuracy Evaluation

1. Fix Gemini quota or use a paid/project quota so current `general_v3` Tier 2 can run.
2. Fix PostgreSQL credentials or serialize SQLite writes before larger batch evaluation.
3. Build `eval/gold_labels.csv` with 100 to 200 human-labeled ticker-date examples.
4. Add historical as-of-date snapshots so evaluation avoids lookahead bias.
5. Compute future 30-day and 1-year excess returns for each ticker-date.
6. Re-run metrics:
   - Tier 1A macro F1
   - Tier 1B tone/guidance/key-driver F1
   - Tier 2 directional accuracy
   - high-confidence hit rate
   - Sharpe ratio
   - excess return by signal class
   - calibration error
