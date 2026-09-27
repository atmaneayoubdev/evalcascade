# Benchmark: halueval-groundedness-cascade-0.6

- Date (UTC): 2026-09-27 18:52
- EvalCascade: 0.1.0
- Dataset: `halueval_groundedness` (150 labeled cases, hash `6124dea54a693cdd`)
- Metric: `groundedness` (pass threshold 0.6; params {'max_passage_chars': 8000})
- Cascade escalation threshold: 0.6 · concurrency 6
- Evaluator `jev`: kind=system_one, model=typesafe/jev-1.13, surface=decisions
- Evaluator `llm`: kind=llm_judge, provider=openai_compatible, model=qwen3.8-27b, structured_output=json_schema

| Mode | n | Errors | Accuracy (95% CI) | Precision | Recall | F1 | Brier ↓ | ECE ↓ | p50 latency | p95 latency | Total cost | Cost / item | Escalated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Adaptive cascade | 150 | 0 | 0.813 (0.74-0.87) | 0.764 | 0.907 | 0.829 | 0.176 | 0.156 | 396 ms | 2259 ms | $0.058913 | $0.000393 | 41% |

## Reliability (P(pass) calibration)

**Adaptive cascade** — [0.0-0.1): n=53, p̄=0.03, obs=0.09, [0.1-0.2): n=3, p̄=0.12, obs=0.33, [0.2-0.3): n=4, p̄=0.23, obs=0.25, [0.3-0.4): n=1, p̄=0.30, obs=0.00, [0.8-0.9): n=1, p̄=0.88, obs=1.00, [0.9-1.0): n=88, p̄=0.97, obs=0.76

## Notes

- Measured cascade run at a tuned escalate_below=0.6 (the main report's counterfactual sweep predicted ~41% escalation at this threshold). Same dataset, metric and evaluators as 2026-09-27-halueval-groundedness.
- LLM judge: qwen3.8-27b on a private OpenAI-compatible endpoint with thinking disabled, temperature 0, strict JSON schema. Judge cost is an ESTIMATE at OpenRouter's listed qwen/qwen3.8-27b price ($0.42/M in, $3.00/M out); Jev cost is provider-reported.
- The judge endpoint URL was redacted from this public report (private endpoint); no measured values were changed.
