# Benchmark data

## `halueval_groundedness.jsonl`

150 labeled cases (75 grounded / 75 hallucinated) for the `groundedness` metric, derived from
**HaluEval** — Li et al., 2023, *HaluEval: A Large-Scale Hallucination Evaluation Benchmark for
Large Language Models* — <https://github.com/RUCAIBox/HaluEval>, released under the MIT License
(see [`LICENSE-HaluEval.txt`](LICENSE-HaluEval.txt); Copyright (c) 2020 RUCAIBox).

- 50 QA pairs (`HaluEval/qa`): `knowledge` → `context`, `question` → `input`, and each of
  `right_answer` (label `true`) / `hallucinated_answer` (label `false`) → `output`.
- 25 summarization pairs (`HaluEval/summarization`, documents ≤ 6,000 characters):
  `document` → `context`, `right_summary` (label `true`) / `hallucinated_summary` (label `false`)
  → `output`.
- Sampled with seed `20260927`; case ids are label-neutral (`qa-017-a`/`-b` in random order).
  Only `input`, `output` and `context` are sent to evaluators.

Regenerate with `uv run python benchmarks/prepare_halueval.py` (downloads the source files into
`benchmarks/.cache/`, which is git-ignored).

**Known limitations of the source labels.** HaluEval's labels come from its construction process
(right answers vs. LLM-generated hallucinations), not from per-case human review of our metric.
Some QA knowledge snippets underdetermine the right answer, and QA right answers are much shorter
than hallucinated ones (median 2 vs. 9 words), a surface cue a judge could exploit. Treat results
as a comparison between evaluator strategies on the same data, not as an absolute accuracy claim.
