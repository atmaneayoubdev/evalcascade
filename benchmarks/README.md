# Benchmarks

EvalCascade ships a benchmark harness that compares three evaluation strategies on the same
labeled data:

| Mode | Policy | What it measures |
|---|---|---|
| **Jev only** | `EvaluationPolicy.jev_only()` | TypeSafe Jev (System One) judges every case |
| **LLM judge only** | `EvaluationPolicy.llm_only()` | a generative LLM judge (System Two) judges every case |
| **Adaptive cascade** | `EvaluationPolicy(escalate_below=τ)` | Jev first; escalate to the LLM judge when Jev's confidence < τ |

## Methodology

- **Data.** A benchmark dataset is a normal EvalCascade JSONL dataset where each case carries a
  gold label in `expected.label` (`true` = the output should pass the metric). The committed set,
  [`data/halueval_groundedness.jsonl`](data/halueval_groundedness.jsonl), has 150 cases (75 / 75)
  derived from HaluEval (MIT); see [`data/README.md`](data/README.md) for provenance and label
  limitations.
- **Prediction.** A case is predicted to pass when the metric score ≥ the metric's pass threshold
  (0.6 for `groundedness`).
- **Quality.** Accuracy with a 95% Wilson interval, precision, recall and F1 (positive class =
  passes), plus an **exact McNemar test** on per-case correctness for every pair of modes — the
  modes judge the same cases, so differences must be tested as paired.
- **Calibration.** Brier score and expected calibration error (10 equal-width bins) of the
  predicted probability that the case passes (`Judgment.pass_probability`). For Jev this comes
  from its probability distribution over score levels; for the LLM judge it comes from its
  self-reported confidence.
- **Latency.** Client-side wall-clock per metric evaluation (every evaluator call for the case,
  including escalation), reported as p50/p95.
- **Cost.** Provider-reported cost when available (OpenRouter reports it for Jev). When an
  endpoint reports no cost, cost is estimated from configured per-token prices and labelled as an
  estimate.
- **Threshold sweep.** A counterfactual replay of the recorded Jev-only and LLM-only judgments at
  other escalation thresholds. Jev's confidences vary slightly between repeated calls, so the sweep
  approximates rather than reproduces a measured cascade — measured cascade runs are reported
  separately.

## Results (2026-09-27)

Real runs, saved verbatim in [`results/`](results/):

- [`2026-09-27-halueval-groundedness.md`](results/2026-09-27-halueval-groundedness.md) — all
  three modes, cascade at the default `escalate_below = 0.82`, plus the threshold sweep.
- [`2026-09-27-halueval-groundedness-cascade-0.6.md`](results/2026-09-27-halueval-groundedness-cascade-0.6.md)
  — a measured cascade run at a tuned `escalate_below = 0.6`.

Configuration: Jev `typesafe/jev-1.13` via OpenRouter's Decisions API; LLM judge `qwen3.8-27b` on
an OpenAI-compatible endpoint (thinking disabled, temperature 0, strict JSON schema); metric
`groundedness` with `max_passage_chars=8000`; concurrency 6.

| Mode | Accuracy (95% CI) | F1 | Brier ↓ | ECE ↓ | p50 latency | p95 latency | Cost / case | Escalated |
|---|---|---|---|---|---|---|---|---|
| Jev only | 0.800 (0.73–0.86) | 0.815 | 0.146 | 0.123 | 373 ms | 530 ms | $0.000034 | — |
| LLM judge only | 0.807 (0.74–0.86) | 0.822 | 0.180 | 0.173 | 1445 ms | 2166 ms | $0.000760* | — |
| Cascade, τ = 0.82 | 0.820 (0.75–0.87) | 0.834 | 0.169 | 0.157 | 1535 ms | 2361 ms | $0.000553* | 60% |
| Cascade, τ = 0.6 | 0.813 (0.74–0.87) | 0.829 | 0.176 | 0.156 | 396 ms | 2259 ms | $0.000393* | 41% |

\* Includes judge cost **estimated** at OpenRouter's listed price for `qwen/qwen3.8-27b`
($0.42 / M input, $3.00 / M output); the endpoint used reports no cost. Jev cost is
provider-reported.

**What this shows — and what it doesn't.**

- On this sample, accuracy differences between the strategies are **not statistically
  significant** (McNemar p ≥ 0.63 for every pair). Do not read the cascade's higher point estimate
  as an accuracy win.
- Jev alone reached the same accuracy as the LLM judge at roughly **1/22 of the (estimated) cost
  and 1/4 of the median latency**, with a lower Brier score and ECE.
- At the default `τ = 0.82`, 60% of groundedness cases escalated: Jev's confidence on 4-level
  score questions is often below 0.82. A tuned `τ = 0.6` escalated 41%, kept accuracy, and cut the
  median latency to Jev's range. **Tune `escalate_below` per metric** (the sweep shows the trade-off).
- 150 cases from one public benchmark is a small sample of one task. Results will differ for
  other metrics, datasets, judges and deployments.

## Reproduce

```bash
# optional: regenerate the dataset from the HaluEval source files
uv run python benchmarks/prepare_halueval.py

# needs OPENROUTER_API_KEY (Jev) and a judge (OpenRouter by default, or any OpenAI-compatible endpoint)
export EVALCASCADE_JUDGE_BASE_URL=https://your-endpoint/v1   # optional
export EVALCASCADE_JUDGE_API_KEY=...                          # optional
export EVALCASCADE_JUDGE_MODEL=your-model                     # optional
uv run python benchmarks/run_benchmark.py \
    --dataset benchmarks/data/halueval_groundedness.jsonl \
    --metric groundedness --param max_passage_chars=8000

# recompute statistics from a saved run without any API calls
uv run python benchmarks/run_benchmark.py --rescore benchmarks/results/<file>.json
```

The Jev part of a full three-mode run over 150 cases cost about **$0.01** in OpenRouter credit.
