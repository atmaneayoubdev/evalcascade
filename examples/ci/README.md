# Regression gates in CI

[`evalcascade-gate.yml`](evalcascade-gate.yml) is a GitHub Actions workflow you can copy.
On every pull request it evaluates your dataset, compares the result with a **committed
baseline**, writes a report to the job summary and fails the job when quality regresses.

## How it works

```text
evalcascade run <dataset> ... -o candidate.json      # evaluate the current code
evalcascade gate --baseline evals/baseline.json \
                 --candidate candidate.json ...      # exit 0 = ok, 1 = regression, 2 = error
```

The gate compares the two experiment exports. Nothing is re-evaluated. With the default
settings it fails when:

- the overall score drops by more than `--max-quality-drop` (absolute, on the 0-1 scale),
- a metric listed with `--metric-threshold name=value` drops by more than its value,
- any optional limit is exceeded: `--max-metric-drop`, `--max-cost-increase`,
  `--max-latency-increase`, `--min-score`, `--max-escalation-rate`, or
  `--require-same-dataset`.

See [docs/cli.md](../../docs/cli.md#evalcascade-gate) for every option.

## 1. Create and commit a baseline

Run the suite once on a known-good version of your system, then export the experiment:

```bash
export OPENROUTER_API_KEY=...                      # or put it in .env
evalcascade run datasets/my_dataset.jsonl --suite rag --name baseline
evalcascade experiments export baseline -o evals/baseline.json
git add evals/baseline.json
git commit -m "chore(evals): add evaluation baseline"
```

`experiments export` accepts any experiment reference: an id, an id prefix, a name (the
most recent experiment with that name) or `latest`. You can also write the export directly
with `evalcascade run ... -o evals/baseline.json`.

The export is a self-contained JSON file with the summary, the per-case results, the metric
configuration, the policy and the evaluator models. It never contains API keys, but it does
contain your dataset's inputs, outputs and context, so treat it like the dataset itself.

## 2. Add the workflow

1. Copy `evalcascade-gate.yml` to `.github/workflows/` in your repository.
2. Add a repository secret named `OPENROUTER_API_KEY`.
3. Set `EVAL_DATASET` to your dataset, and change `--suite` / `--metric` and the thresholds
   to match how you created the baseline. Compare like with like: same dataset, same
   metrics, same policy.

The workflow skips pull requests from forks, because they receive no secrets. Keep it on
`pull_request`. Never use `pull_request_target` for jobs that hold API keys.

## 3. Update the baseline deliberately

When a change improves quality, or you accept a trade-off, refresh the baseline in the same
pull request:

```bash
evalcascade run datasets/my_dataset.jsonl --suite rag --name baseline -o evals/baseline.json
```

Each run uploads `candidate.json` as a workflow artifact. You can also download it and
promote it to the baseline:

```bash
cp candidate.json evals/baseline.json
evalcascade experiments import evals/baseline.json   # optional: inspect it locally / in the dashboard
```

## Tips

- **Noise.** LLM-based judgments vary a little between runs. Start with
  `--max-quality-drop 0.03` and tighten it once you know your dataset's run-to-run variance.
  Larger datasets give more stable scores.
- **Per-metric limits.** Guard the metric you care most about, for example
  `--metric-threshold groundedness=0.05` for RAG, or use `--max-metric-drop` to cover every
  metric.
- **Cost and latency.** Add `--max-cost-increase 0.2` (+20 %) or `--max-latency-increase 0.5`
  to catch runaway escalations or slower responses.
- **Offline gates.** `evalcascade gate` only reads the two JSON files. It needs no API key and
  makes no network calls, so you can also gate on experiments produced elsewhere.
- **Local preview.** Run `evalcascade compare evals/baseline.json candidate.json` for the full
  comparison table, or `evalcascade gate ... --format markdown` to see the report CI will post.
