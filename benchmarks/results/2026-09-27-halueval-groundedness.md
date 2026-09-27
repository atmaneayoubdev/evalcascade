# Benchmark: halueval-groundedness

- Date (UTC): 2026-09-27 18:49
- EvalCascade: 0.1.0
- Dataset: `halueval_groundedness` (150 labeled cases, hash `6124dea54a693cdd`)
- Metric: `groundedness` (pass threshold 0.6; params {'max_passage_chars': 8000})
- Cascade escalation threshold: 0.82 · concurrency 6
- Evaluator `jev`: kind=system_one, model=typesafe/jev-1.13, surface=decisions
- Evaluator `llm`: kind=llm_judge, provider=openai_compatible, model=qwen3.8-27b, structured_output=json_schema

| Mode | n | Errors | Accuracy (95% CI) | Precision | Recall | F1 | Brier ↓ | ECE ↓ | p50 latency | p95 latency | Total cost | Cost / item | Escalated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Jev only | 150 | 0 | 0.800 (0.73-0.86) | 0.759 | 0.880 | 0.815 | 0.146 | 0.123 | 373 ms | 530 ms | $0.005044 | $0.000034 | — |
| LLM judge only | 150 | 0 | 0.807 (0.74-0.86) | 0.761 | 0.893 | 0.822 | 0.180 | 0.173 | 1445 ms | 2166 ms | $0.114029 | $0.000760 | — |
| Adaptive cascade | 150 | 0 | 0.820 (0.75-0.87) | 0.773 | 0.907 | 0.834 | 0.169 | 0.157 | 1535 ms | 2361 ms | $0.082906 | $0.000553 | 60% |

## Paired significance (exact McNemar test on per-case correctness)

| Comparison | Cases | Only A correct | Only B correct | p-value |
| --- | --- | --- | --- | --- |
| Jev only (A) vs LLM judge only (B) | 150 | 7 | 8 | 1.000 |
| Jev only (A) vs Adaptive cascade (B) | 150 | 7 | 10 | 0.629 |
| LLM judge only (A) vs Adaptive cascade (B) | 150 | 2 | 4 | 0.688 |

## Escalation-threshold sweep (counterfactual)

Replays the recorded Jev-only and LLM-only judgments: a case uses Jev's verdict when its confidence is at least the threshold, otherwise the LLM judge's. Latency and cost add the LLM call for escalated cases.

| escalate_below | Escalated | Accuracy | F1 | Total cost | p50 latency | p95 latency |
| --- | --- | --- | --- | --- | --- | --- |
| 0.5 | 31% | 0.793 | 0.810 | $0.044284 | 400 ms | 2338 ms |
| 0.6 | 41% | 0.793 | 0.807 | $0.057630 | 436 ms | 2357 ms |
| 0.7 | 49% | 0.800 | 0.815 | $0.068243 | 1032 ms | 2467 ms |
| 0.75 | 55% | 0.807 | 0.822 | $0.076566 | 1525 ms | 2536 ms |
| 0.8 | 59% | 0.807 | 0.822 | $0.080255 | 1587 ms | 2536 ms |
| 0.82 | 60% | 0.807 | 0.822 | $0.081470 | 1608 ms | 2536 ms |
| 0.85 | 63% | 0.807 | 0.822 | $0.085197 | 1657 ms | 2536 ms |
| 0.9 | 70% | 0.807 | 0.822 | $0.091283 | 1704 ms | 2536 ms |
| 0.95 | 79% | 0.807 | 0.822 | $0.100583 | 1742 ms | 2536 ms |
| 0.99 | 93% | 0.807 | 0.822 | $0.112967 | 1818 ms | 2658 ms |
| 1 | 99% | 0.807 | 0.822 | $0.118585 | 1818 ms | 2658 ms |

## Reliability (P(pass) calibration)

**Jev only** — [0.0-0.1): n=35, p̄=0.02, obs=0.03, [0.1-0.2): n=9, p̄=0.14, obs=0.44, [0.2-0.3): n=4, p̄=0.24, obs=0.25, [0.3-0.4): n=6, p̄=0.33, obs=0.17, [0.4-0.5): n=4, p̄=0.47, obs=0.25, [0.5-0.6): n=6, p̄=0.56, obs=0.33, [0.6-0.7): n=9, p̄=0.65, obs=0.11, [0.7-0.8): n=8, p̄=0.74, obs=0.50, [0.8-0.9): n=12, p̄=0.85, obs=0.75, [0.9-1.0): n=57, p̄=0.97, obs=0.89

**LLM judge only** — [0.0-0.1): n=62, p̄=0.03, obs=0.13, [0.8-0.9): n=1, p̄=0.85, obs=0.00, [0.9-1.0): n=87, p̄=0.99, obs=0.77

**Adaptive cascade** — [0.0-0.1): n=61, p̄=0.03, obs=0.11, [0.1-0.2): n=1, p̄=0.11, obs=0.00, [0.9-1.0): n=88, p̄=0.98, obs=0.77

## Notes

- Gold labels come from HaluEval's construction (right vs. hallucinated responses), not per-case human review; see benchmarks/data/README.md for known label limitations.
- LLM judge: qwen3.8-27b on a private OpenAI-compatible endpoint with thinking disabled (chat_template_kwargs.enable_thinking=false), temperature 0, strict JSON schema.
- Jev cost is provider-reported by OpenRouter. The judge endpoint reports no cost, so judge cost is an ESTIMATE at OpenRouter's listed price for qwen/qwen3.8-27b ($0.42/M input, $3.00/M output, retrieved 2026-09-27).
- Latency is client-side wall-clock per metric evaluation (all evaluator calls for the case, including escalation) at concurrency 6 from one machine; Jev and the judge are served from different infrastructure, so latency differences reflect deployment as well as model.
- Jev confidences vary slightly between repeated calls, so the counterfactual sweep approximates rather than reproduces the measured cascade run.
- The judge endpoint URL was redacted from this public report (private endpoint); no measured values were changed.
