# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-27

First public release.

### Added

- **Evaluation cascade (System One → System Two).**
  - Each metric is checked deterministically first when possible, then judged by Jev.
  - It is escalated to a generative LLM judge only when Jev's confidence is below
    `escalate_below` (default `0.82`) or Jev fails.
  - Rubrics that need deeper reasoning can go straight to the judge.
  - Every judgment in the chain is recorded with its route (`deterministic`, `jev`, `llm`,
    `jev_to_llm`), escalation reason, confidence, latency and cost.
- **`EvaluationPolicy`.**
  - Presets `cascade`, `jev`, `llm` and `deterministic`.
  - `escalate_on_error` and `route_reasoning_to_fallback` switches.
  - Per-metric overrides (`MetricPolicy`) and per-metric-instance escalation thresholds.
- **Provider-independent rubric primitives:** `BinaryQuestion`, `ChoiceQuestion` and
  `ScoreQuestion`.
  - Every backend answers the same typed questions.
  - Scores are normalized to `[0, 1]`.
  - The confidence source is tracked: `provider`, `derived`, `self_reported` or
    `deterministic`.
- **13 built-in metrics:**
  - General: `answer_relevance`, `correctness`, `task_completion`, `safety`.
  - RAG: `groundedness` (response- or sentence-level), `context_relevance`,
    `citation_presence`, `citation_correctness`.
  - Agents: `tool_selection`, `tool_arguments_quality`, `trajectory_efficiency`,
    `task_success`, `unnecessary_tool_calls`.
  - Metric bundles `general`, `rag` and `agent`.
  - Agent metrics report per-step outcomes for trace annotation.
- **Jev evaluator (TypeSafe System One via OpenRouter).**
  - Uses the Decisions API (`POST /api/alpha/decisions`), with the alternative
    `/api/v1/systemone` surface available.
  - Question-type mapping: `noul`, `choice`, `score`.
  - All Jev-routed metrics of a case are batched into one request, with shared cost
    apportioned by question count.
  - Responses are validated against a typed schema.
- **LLM judge for any OpenAI-compatible chat completions endpoint** (`LLMJudge`), plus an
  OpenRouter preset (`OpenRouterLLMJudge`).
  - Strict JSON-schema structured output, with automatic downgrade to `json_object` and then
    prompt-only JSON.
  - Invalid replies get corrective retries.
  - Cost comes from the provider when reported, or is estimated from configured per-token
    prices (`cost_source`).
- **Supporting evaluators.**
  - Deterministic evaluator.
  - Simulated evaluator for clearly labelled demo data.
  - Registry for custom evaluator backends.
- **Resilient provider HTTP client.**
  - Timeouts on every request.
  - Bounded retries with exponential backoff and jitter, honouring `Retry-After`.
  - Typed errors: authentication, credits, rate limit, timeout, response validation.
  - Bounded concurrency.
- **Datasets.**
  - JSONL (or JSON list) with `input`, `output`, `context`, `expected`, `trace` (agent steps,
    tool calls and tool specs) and `metadata`.
  - Validation with line-numbered errors and a content hash.
  - Three bundled sample datasets (`rag_qa`, `agent_tasks`, `support_bot`), referenced as
    `sample:<name>`.
  - Dataset templates.
- **Experiments.**
  - Per-metric statistics: mean, std, min/max, pass rate, histogram.
  - Routing rates: deterministic share, Jev acceptance, escalation, LLM share, plus
    Jev-vs-judge agreement.
  - Latency p50/p95 and cost with a completeness flag.
  - JSON export/import for CI baselines.
  - Comparisons with case-level regressions and improvements.
- **Regression gate.**
  - Limits on overall score drop and per-metric drop.
  - Optional limits on cost increase, p95 latency increase, minimum score and escalation
    rate, plus a same-dataset check.
  - Text, JSON and Markdown output, including a GitHub step summary.
  - Exits with code 1 on regression.
- **Local SQLite storage** (SQLAlchemy) for datasets and experiments. Experiments can be
  referenced by id, id prefix, name, `latest` or `latest~N`.
- **CLI** (`evalcascade`): `init`, `demo`, `doctor` (optionally `--live`), `evaluate`,
  `run`, `datasets list|import|create|show|validate`,
  `experiments list|show|export|import|delete`, `compare`, `gate`, `metrics` and `serve`.
- **Local API** (FastAPI) served by `evalcascade serve`.
  - Endpoints for health, configuration, the metric catalog, evaluation, datasets,
    experiments, cases, comparison, gates and the dashboard overview.
  - OpenAPI docs at `/docs`.
  - Optional bearer-token auth (`EVALCASCADE_API_TOKEN`).
  - Serves the bundled dashboard.
- **Local web dashboard** (Next.js static export in `web/`), plus
  `scripts/build_dashboard.py` to bundle it into the Python package.
- **Python API:** `EvalSuite` / `EvaluationSuite` with `evaluate`, `evaluate_many`, `run`
  (optionally generating outputs with a `task` callback), and `*_sync` helpers.
- **Runnable SDK examples** in `examples/`: basic, RAG, agent, cascade and dataset workflows.
- **Benchmark harness** (`evalcascade.benchmarking`, `benchmarks/`).
  - Compares Jev-only, LLM-judge-only and the adaptive cascade on labelled data.
  - Reports accuracy with Wilson intervals, precision/recall/F1, exact McNemar tests,
    Brier score and ECE, latency p50/p95 and cost.
  - Includes an escalation-threshold sweep.
  - Ships a 150-case HaluEval-derived groundedness set with recorded results.
- **Configuration** via `evalcascade.toml` (`[evalcascade]`, `[policy]`, `[jev]`,
  `[judge]`, `[metrics.<name>]`), environment variables and `.env`. Precedence: defaults <
  file < environment < explicit arguments.
- **Security measures.**
  - Secrets only from the environment, held as `SecretStr`.
  - Keys only go to their own endpoint: `OPENROUTER_API_KEY` is sent to `https://openrouter.ai`
    hosts only, and a custom judge endpoint uses only `EVALCASCADE_JUDGE_API_KEY` (or none,
    with `EVALCASCADE_JUDGE_REQUIRE_API_KEY=false`).
  - Log and error redaction.
  - No secrets in the database, exports or API responses.
  - Evaluated text is kept separate from judge instructions.
  - The API binds to `127.0.0.1` by default and warns when it is exposed without a token.
- **Packaging and tooling.**
  - Multi-stage Docker image (non-root) and `docker-compose.yml`.
  - GitHub Actions CI: lint, tests on Linux and Windows, build, web, Docker, gate self-test.
  - A copy-paste regression-gate workflow for users (`examples/ci/`).
  - Pre-commit hooks.
  - Reference documentation in `docs/`.

[Unreleased]: https://github.com/atmaneayoubdev/evalcascade/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/atmaneayoubdev/evalcascade/releases/tag/v0.1.0
