# Local API

`evalcascade serve` starts a FastAPI server that backs the dashboard and can be scripted
directly:

```bash
evalcascade serve                         # http://127.0.0.1:8000
```

- **Interactive OpenAPI docs:** <http://127.0.0.1:8000/docs> (ReDoc at `/redoc`, schema at
  `/openapi.json`). The schema is generated from the code and is authoritative.
- **TypeScript contract:** [`docs/api-contract.ts`](api-contract.ts) holds the types the
  dashboard consumes.
- **Conventions:** JSON everywhere. Timestamps are ISO-8601 UTC, scores are normalized to
  `[0, 1]`, costs are USD and latencies are milliseconds.
- **Dashboard:** served at `/` when a bundle is found (see
  [cli.md](cli.md#evalcascade-serve)). Otherwise `/` returns a small JSON pointer to `/docs`.

The app factory is `evalcascade.api.app:create_app`, if you want to run it under your own
ASGI server:

```bash
uvicorn evalcascade.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

## Authentication

By default the server binds to `127.0.0.1` and needs no authentication. To expose it
beyond localhost, for example in Docker, set a token:

```bash
export EVALCASCADE_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
evalcascade serve --host 0.0.0.0
```

Every data endpoint then requires the header `Authorization: Bearer <token>`. Missing or
wrong tokens get `401`, and the token is compared in constant time. These routes never
require the token, because they expose no data or secrets:

- `GET /api/health`
- `GET /api/metrics`
- `GET /api/metrics/suites`
- `/docs`, `/redoc`, `/openapi.json`
- the static dashboard files

`evalcascade serve` warns when you bind to a non-local address without a token. Anyone who
can reach the port could run evaluations billed to your API keys and read your datasets and
results.

Browser access from other origins is limited by CORS to `http://localhost:3000` and
`http://127.0.0.1:3000` (the dashboard dev server). Configure it with `cors_origins` in
`evalcascade.toml`.

## Errors

Errors return `{"detail": "..."}`:

| Status | When |
| --- | --- |
| `400` | Configuration or dataset problem: unknown metric, missing API key for the chosen policy, invalid cases, dataset already exists |
| `401` | Missing or invalid bearer token |
| `404` | Experiment, case or dataset not found |
| `422` | Request body or query parameters failed validation |
| `502` | Upstream provider failure that was not handled per metric |

Provider failures during an evaluation normally don't fail the request. The affected
metric reports `status: "error"` with a `message`, or is escalated to the fallback judge.

## Endpoints

| Method | Path | Auth | Returns |
| --- | --- | --- | --- |
| GET | `/api/health` | no | `Health` |
| GET | `/api/config` | yes | `ConfigSummary` (secret-free) |
| GET | `/api/metrics` | no | `MetricInfo[]` |
| GET | `/api/metrics/suites` | no | `{suite: metric[]}` |
| POST | `/api/evaluate` | yes | `EvaluationResult` |
| GET | `/api/datasets` | yes | `DatasetInfo[]` |
| POST | `/api/datasets` | yes | `DatasetInfo` (201) |
| GET | `/api/datasets/{name}?limit&offset` | yes | `DatasetDetail` |
| GET | `/api/experiments?include_demo&limit&name` | yes | `ExperimentListItem[]` |
| GET | `/api/experiments/{ref}` | yes | experiment detail (summary + configuration, no per-case results) |
| DELETE | `/api/experiments/{ref}` | yes | `{"deleted": "<id>"}` |
| GET | `/api/experiments/{ref}/cases?limit&offset&filter` | yes | `Page<CaseResultRow>` |
| GET | `/api/experiments/{ref}/cases/{case_id}` | yes | `CaseResult` |
| GET | `/api/compare?baseline&candidate` | yes | `Comparison` |
| POST | `/api/gate` | yes | `GateResult` |
| GET | `/api/overview?include_demo` | yes | `Overview` |

`{ref}` accepts an experiment id, a unique id prefix, an experiment name (the most recent
with that name), `latest` or `latest~N`.

The examples below assume:

```bash
API=http://127.0.0.1:8000
AUTH=()                                              # no token configured
# AUTH=(-H "Authorization: Bearer $EVALCASCADE_API_TOKEN")
```

### Health and configuration

```bash
curl -s $API/api/health
# {"status":"ok","version":"0.1.0","database":"ok"}

curl -s "${AUTH[@]}" $API/api/config
```

`GET /api/config` returns the version, the (redacted) database URL, and **whether** the
OpenRouter and judge keys are set (`openrouter_api_key_configured`,
`judge_api_key_configured`). It also returns `api_auth_enabled`, the config file path, the
Jev and judge settings and the policy. Key values are never returned.

### Metric catalog

```bash
curl -s $API/api/metrics          # name, category, primitives, deterministic, required_fields, default_threshold, ...
curl -s $API/api/metrics/suites   # {"general": [...], "rag": [...], "agent": [...]}
```

### `POST /api/evaluate`

Evaluates one interaction. The body fields are:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `input`, `output` | string | `null` | Prompt and system output. |
| `context` | string[] | `[]` | Retrieved passages. |
| `expected` | object or string | `null` | Ground truth (a string means `{"answer": ...}`). |
| `trace` | object | `null` | Agent trace (`steps`, `tools`). |
| `metadata` | object | `{}` | Free-form. |
| `metrics` | array | `["answer_relevance"]` | Metric names, suite names (`general`, `rag`, `agent`), or `{"name": ..., "params": {...}}` objects. |
| `policy` | string | server config | `cascade`, `jev`, `llm` or `deterministic`. |
| `escalate_below` | number | server config | Escalation threshold, 0-1. |

```bash
curl -s "${AUTH[@]}" -X POST $API/api/evaluate -H "Content-Type: application/json" -d '{
  "input": "How long are backups kept?",
  "output": "Backups are kept for 30 days [1].",
  "context": ["Automated backups are retained for 30 days."],
  "metrics": ["rag", {"name": "citation_correctness", "params": {"max_citations": 5}}],
  "policy": "cascade"
}'
```

Each metric may appear once, after suites are expanded. To use one metric twice with
different parameters, give the second copy an `alias`, for example
`{"name": "groundedness", "params": {"granularity": "sentence", "alias": "groundedness_sentences"}}`.
Otherwise the request fails with `400`.

The response is an `EvaluationResult` with `overall_score`, `passed`, `latency_ms`,
`cost_usd`, `escalations` and one entry in `metrics[]` per metric. Each entry holds:

- `score`, `passed`, `threshold`, `status`,
- `route` (`deterministic` / `jev` / `llm` / `jev_to_llm` / `none`),
- `escalated`, `escalation_reason`, `confidence`,
- `judgments[]`: each evaluator's verdict with its answers, model, latency, token usage,
  cost and `cost_source`.

Use `"policy": "deterministic"` to evaluate without any API key.

`[metrics.<name>]` parameters from `evalcascade.toml` apply to metrics given by name. For
`{name, params}` objects, only the params in the request apply.

### Datasets

```bash
curl -s "${AUTH[@]}" $API/api/datasets
curl -s "${AUTH[@]}" "$API/api/datasets/rag_qa?limit=5&offset=0"      # info + a page of cases (limit 1-500)

curl -s "${AUTH[@]}" -X POST $API/api/datasets -H "Content-Type: application/json" -d '{
  "name": "smoke",
  "description": "two quick cases",
  "cases": [{"input": "Hi", "output": "Hello!"}, {"input": "2+2?", "output": "4", "expected": "4"}],
  "overwrite": false
}'
```

The dataset `name` must match `^[A-Za-z0-9][A-Za-z0-9_.-]*$`. Uploaded cases are validated
(`400` with row errors on failure) and stored in `<home>/datasets/<name>.jsonl`.

### Experiments and cases

```bash
curl -s "${AUTH[@]}" "$API/api/experiments?include_demo=false&limit=20"
curl -s "${AUTH[@]}" $API/api/experiments/latest
curl -s "${AUTH[@]}" "$API/api/experiments/baseline/cases?filter=escalated&limit=50&offset=0"
curl -s "${AUTH[@]}" $API/api/experiments/baseline/cases/rag-003
curl -s "${AUTH[@]}" -X DELETE $API/api/experiments/3f9c2a1b7d4e
```

- **List (`GET /api/experiments`):** newest first. `limit` is 1-1000, default 100.
  `include_demo` defaults to `true`, and `name` filters by exact name.
- **Case rows (`GET /api/experiments/{ref}/cases`):** compact rows with per-metric score,
  pass, route and status. `filter` is `all`, `passed`, `failed` or `escalated`; `limit` is
  1-500, default 50.
- **Case detail (`GET /api/experiments/{ref}/cases/{case_id}`):** the full `CaseResult`,
  with the case itself and every judgment.

### Compare and gate

```bash
curl -s "${AUTH[@]}" "$API/api/compare?baseline=baseline&candidate=latest"

curl -s "${AUTH[@]}" -X POST $API/api/gate -H "Content-Type: application/json" -d '{
  "baseline": "baseline",
  "candidate": "latest",
  "max_quality_drop": 0.03,
  "metric_thresholds": {"groundedness": 0.05},
  "max_metric_drop": null,
  "max_cost_increase": 0.2,
  "max_latency_increase": null,
  "min_score": null,
  "max_escalation_rate": null,
  "require_same_dataset": false
}'
```

`POST /api/gate` always answers `200`. Check `passed`, `checks[]` and `violations[]` in the
body. The API only accepts stored experiment references. To gate exported `.json` files,
use `evalcascade gate` or `experiments import` them first.

### Overview

```bash
curl -s "${AUTH[@]}" "$API/api/overview?include_demo=true"
```

This endpoint aggregates up to 500 recent experiments for the dashboard home page:

- totals, and averages over the 30 most recent experiments,
- route counts, the 10 most recent experiments,
- a trend of up to 30 points (oldest first),
- per-name regression indicators, comparing the latest run with the previous one. A drop in
  overall score of more than 0.03, or of any metric by more than 0.05, flags a regression.

`has_demo_data` and `is_demo` flags keep simulated demo data clearly separated from real
results.
