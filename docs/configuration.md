# Configuration

EvalCascade reads its configuration from four layers. Later layers override earlier ones:

1. built-in defaults,
2. `evalcascade.toml`,
3. environment variables (including those loaded from `.env`),
4. explicit arguments, meaning CLI flags such as `--policy` and `--escalate-below`, or
   keyword arguments to `Settings.load(...)` in Python.

Run `evalcascade doctor` to see the effective configuration. `GET /api/config` returns the
same summary. Neither ever shows key values.

## Where the files are found

- **`evalcascade.toml`:** the path from `--config` / `-c`, otherwise `$EVALCASCADE_CONFIG`,
  otherwise `./evalcascade.toml` in the current directory. A missing explicit path is an
  error. Relative paths inside the file (`home`, `database`) are resolved against the
  file's directory.
- **`.env`:** searched for in the current directory and then each parent directory
  (python-dotenv `find_dotenv`). The first one found is loaded **without overriding**
  variables that are already set. Set `EVALCASCADE_DISABLE_DOTENV=1` (or `true`) to skip
  it, which is recommended in CI and containers. Start from [`.env.example`](../.env.example).

API keys and tokens are **never** read from `evalcascade.toml`. A `[judge] api_key` entry
is rejected with an error. Put keys in the environment or `.env`.

## `evalcascade.toml`

`evalcascade init` writes a commented starter file. Every section is optional.

```toml
[evalcascade]
home = ".evalcascade"            # workspace: SQLite database + imported datasets
# database = "evals.db"          # SQLite file (relative to this file) or a full SQLAlchemy URL
# database_url = "sqlite:////abs/path/evalcascade.db"
# cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

[policy]
deterministic_first = true
primary = "jev"                  # System One judge
fallback = "llm"                 # generative judge used on escalation
escalate_below = 0.82            # escalate when Jev's confidence is below this
escalate_on_error = true
route_reasoning_to_fallback = true

[policy.overrides.groundedness]  # per-metric policy (keyed by metric name or alias)
escalate_below = 0.9

[jev]
model = "typesafe/jev-1.13"
surface = "decisions"            # or "systemone"
timeout_s = 30

[judge]
provider = "openrouter"          # or "openai_compatible" (then also set base_url)
model = "openai/gpt-4.1-mini"
temperature = 0.0

[metrics.groundedness]           # constructor parameters for one metric
threshold = 0.7
granularity = "sentence"
```

### `[evalcascade]`

| Key | Default | Description |
| --- | --- | --- |
| `home` | `.evalcascade` | Workspace directory for the SQLite database and imported datasets. Relative to the TOML file. |
| `database` | none | SQLite file path relative to the TOML file, or a full SQLAlchemy URL (if it contains `://`). Takes precedence over `database_url`. |
| `database_url` | `sqlite:///<home>/evalcascade.db` | SQLAlchemy database URL. |
| `cors_origins` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | Origins allowed to call the local API from a browser. |

Other keys in this section are ignored.

### `[policy]`

| Key | Default | Description |
| --- | --- | --- |
| `deterministic_first` | `true` | Use a metric's deterministic check when it can decide. Fully deterministic metrics always use it. |
| `primary` | `"jev"` | Evaluator used first for semantic judgment. |
| `fallback` | `"llm"` | Evaluator used on escalation. |
| `escalate_below` | `0.82` | Escalate when the primary judgment's confidence is below this value, or missing. |
| `escalate_on_error` | `true` | Escalate when the primary evaluator fails. |
| `route_reasoning_to_fallback` | `true` | Send rubrics flagged "requires reasoning" straight to the fallback. For example, `correctness` without a reference answer. |
| `overrides.<metric>` | none | Per-metric `deterministic_first`, `primary`, `fallback`, `escalate` (`false` = never escalate) and `escalate_below`. |

Evaluator names are:

- `jev`: TypeSafe Jev via OpenRouter.
- `llm`: the configured `[judge]`.
- `openrouter`: the OpenRouter judge explicitly.
- `deterministic`: deterministic checks.
- Custom names registered from Python.

The escalation threshold is resolved in this order, highest priority first:

1. `policy.overrides.<metric>.escalate_below`
2. the metric's own `escalate_below` (for example from `[metrics.<name>]`)
3. `policy.escalate_below`

TOML has no null value. To disable the fallback, use `EVALCASCADE_FALLBACK=none`, or the
`--policy jev` preset on the command line.

### `[jev]`

| Key | Default | Description |
| --- | --- | --- |
| `model` | `typesafe/jev-1.13` | Jev model id on OpenRouter. |
| `surface` | `decisions` | `decisions` → `POST {base_url}/alpha/decisions`; `systemone` → `POST {base_url}/v1/systemone`. |
| `base_url` | `https://openrouter.ai/api` | OpenRouter API base. |
| `timeout_s` | `30` | Per-request timeout in seconds (connect timeout at most 10 s). |
| `max_retries` | `3` | Retries on transient failures, 0-10. |
| `max_concurrency` | `8` | Maximum concurrent requests. |
| `batch` | `true` | Send all Jev-routed metrics of a case in one request. |
| `max_questions_per_request` | `32` | Upper bound on questions per batched request. |

### `[judge]`

| Key | Default | Description |
| --- | --- | --- |
| `provider` | `openrouter` | `openrouter`, or `openai_compatible` for any other OpenAI-compatible endpoint. |
| `model` | `openai/gpt-4.1-mini` | Judge model id. |
| `base_url` | `https://openrouter.ai/api/v1` | Chat completions base URL. Requests go to `{base_url}/chat/completions`. |
| `timeout_s` | `60` | Per-request timeout in seconds. |
| `max_retries` | `3` | Retries on transient failures, 0-10. |
| `max_concurrency` | `8` | Maximum concurrent requests. |
| `temperature` | `0.0` | Sampling temperature, 0-2. |
| `max_tokens` | `1024` | Completion token limit (at least 64). |
| `structured_output` | `json_schema` | `json_schema`, `json_object` or `prompt`. The judge downgrades automatically if the endpoint rejects the mode. |
| `parse_retries` | `2` | Corrective retries after an invalid reply, 0-5. |
| `extra_body` | `{}` | Extra request fields merged into the payload, for example `{ chat_template_kwargs = { enable_thinking = false } }`. |
| `input_cost_per_mtok` | none | USD per million input tokens, used to estimate cost when the endpoint reports none. |
| `output_cost_per_mtok` | none | USD per million output tokens. Both prices are needed for an estimate. |

`api_key` is not allowed here; use `EVALCASCADE_JUDGE_API_KEY`.

> **Using a non-OpenRouter judge from TOML:** always set `provider = "openai_compatible"`
> together with `base_url`. Only the `EVALCASCADE_JUDGE_BASE_URL` environment variable
> switches the provider implicitly. A TOML `base_url` with the default
> `provider = "openrouter"` keeps OpenRouter behaviour, including sending
> `OPENROUTER_API_KEY`, to that URL.

### `[metrics.<name>]`

Constructor parameters for a metric, keyed by its registry name (`groundedness`,
`correctness`, ...). They apply when metrics are built by name: in the CLI and in
`POST /api/evaluate` requests that list metric names.

Every metric accepts these parameters:

- `threshold`: pass threshold on the normalized score.
- `weight`: weight in the overall score.
- `escalate_below`: per-metric escalation threshold.
- `alias`: report the metric under a different key.

Metric-specific parameters are listed in [metrics.md](metrics.md). Unknown parameters are
rejected.

## Environment variables

Empty values are ignored. Booleans accept `1`, `true`, `yes` or `on` (case-insensitive);
anything else is false.

| Variable | Setting | Default | Meaning |
| --- | --- | --- | --- |
| `OPENROUTER_API_KEY` | `openrouter_api_key` | unset | OpenRouter key. Required for Jev; also used by the OpenRouter judge unless `EVALCASCADE_JUDGE_API_KEY` is set. |
| `EVALCASCADE_HOME` | `home` | `.evalcascade` | Workspace directory (relative to the current directory). |
| `EVALCASCADE_DATABASE_URL` | `database_url` | `sqlite:///<home>/evalcascade.db` | SQLAlchemy database URL. |
| `EVALCASCADE_API_TOKEN` | `api_token` | unset | If set, the local API requires `Authorization: Bearer <token>`. |
| `EVALCASCADE_OPENROUTER_BASE_URL` | `jev.base_url` | `https://openrouter.ai/api` | Base URL for Jev requests, and for the `doctor` key check. The judge has its own `EVALCASCADE_JUDGE_BASE_URL`. |
| `EVALCASCADE_JEV_MODEL` | `jev.model` | `typesafe/jev-1.13` | Jev model id. |
| `EVALCASCADE_JEV_SURFACE` | `jev.surface` | `decisions` | `decisions` or `systemone`. |
| `EVALCASCADE_JEV_TIMEOUT` | `jev.timeout_s` | `30` | Jev request timeout (seconds). |
| `EVALCASCADE_JEV_MAX_RETRIES` | `jev.max_retries` | `3` | Jev retries (0-10). |
| `EVALCASCADE_JEV_BATCH` | `jev.batch` | `true` | Batch all Jev-routed metrics of a case into one request. |
| `EVALCASCADE_JUDGE_PROVIDER` | `judge.provider` | `openrouter` | `openrouter` or `openai_compatible`. |
| `EVALCASCADE_JUDGE_MODEL` | `judge.model` | `openai/gpt-4.1-mini` | Judge model id. |
| `EVALCASCADE_JUDGE_BASE_URL` | `judge.base_url` | `https://openrouter.ai/api/v1` | Judge endpoint. Setting it without `EVALCASCADE_JUDGE_PROVIDER` selects `openai_compatible`. |
| `EVALCASCADE_JUDGE_API_KEY` | `judge.api_key` | unset | Judge key. Without it, the `openrouter` provider uses `OPENROUTER_API_KEY`. `openai_compatible` requires it unless `require_api_key` is false (see below). |
| `EVALCASCADE_JUDGE_REQUIRE_API_KEY` | `judge.require_api_key` | `true` | Set `false` for OpenAI-compatible servers without authentication (no `Authorization` header is sent). |
| `EVALCASCADE_JUDGE_TIMEOUT` | `judge.timeout_s` | `60` | Judge request timeout (seconds). |
| `EVALCASCADE_JUDGE_MAX_RETRIES` | `judge.max_retries` | `3` | Judge retries (0-10). |
| `EVALCASCADE_JUDGE_TEMPERATURE` | `judge.temperature` | `0.0` | Judge temperature (0-2). |
| `EVALCASCADE_JUDGE_MAX_TOKENS` | `judge.max_tokens` | `1024` | Judge completion token limit. |
| `EVALCASCADE_JUDGE_STRUCTURED_OUTPUT` | `judge.structured_output` | `json_schema` | `json_schema`, `json_object` or `prompt`. |
| `EVALCASCADE_JUDGE_EXTRA_BODY` | `judge.extra_body` | `{}` | JSON object merged into each judge request. |
| `EVALCASCADE_JUDGE_INPUT_COST_PER_MTOK` | `judge.input_cost_per_mtok` | unset | USD per million input tokens (cost estimate). |
| `EVALCASCADE_JUDGE_OUTPUT_COST_PER_MTOK` | `judge.output_cost_per_mtok` | unset | USD per million output tokens (cost estimate). |
| `EVALCASCADE_PRIMARY` | `policy.primary` | `jev` | Primary evaluator; `none`/`null` disables it. |
| `EVALCASCADE_FALLBACK` | `policy.fallback` | `llm` | Fallback evaluator; `none`/`null` disables escalation. |
| `EVALCASCADE_ESCALATE_BELOW` | `policy.escalate_below` | `0.82` | Escalation threshold (0-1). |

These variables are read outside the settings model:

| Variable | Meaning |
| --- | --- |
| `EVALCASCADE_CONFIG` | Path to `evalcascade.toml` (same as `--config`). |
| `EVALCASCADE_DISABLE_DOTENV` | `1` or `true`: do not load `.env`. |
| `EVALCASCADE_DASHBOARD_DIR` | Directory with a built dashboard (`index.html`); checked first by `evalcascade serve`. |
| `EVALCASCADE_LIVE_TESTS` | `1` enables the opt-in live tests (development only). |

## Examples

**Jev plus a self-hosted judge (vLLM, SGLang, LiteLLM, ...)**

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
export EVALCASCADE_JUDGE_BASE_URL=http://localhost:8001/v1    # implies openai_compatible
export EVALCASCADE_JUDGE_MODEL=Qwen/Qwen3-32B
export EVALCASCADE_JUDGE_REQUIRE_API_KEY=false                 # server has no auth
# export EVALCASCADE_JUDGE_API_KEY=...                         # ...or, if it does
export EVALCASCADE_JUDGE_EXTRA_BODY='{"chat_template_kwargs": {"enable_thinking": false}}'
export EVALCASCADE_JUDGE_INPUT_COST_PER_MTOK=0.40              # optional cost estimate
export EVALCASCADE_JUDGE_OUTPUT_COST_PER_MTOK=1.60
```

An `openai_compatible` judge needs `EVALCASCADE_JUDGE_API_KEY` (sent as
`Authorization: Bearer <key>`) unless `EVALCASCADE_JUDGE_REQUIRE_API_KEY=false`; otherwise the
pre-flight check stops the run with `no API key configured for the 'llm' judge`.

**Key routing is conservative.** `OPENROUTER_API_KEY` is only ever sent to `https://openrouter.ai`
hosts: a judge `base_url` pointing anywhere else — whether set in `evalcascade.toml` or the
environment — switches the provider to `openai_compatible`, which uses only
`EVALCASCADE_JUDGE_API_KEY`. Conversely, the explicit `openrouter` evaluator never receives
`EVALCASCADE_JUDGE_API_KEY` when that key belongs to another endpoint.

**Jev only, never an LLM judge**

```bash
export EVALCASCADE_FALLBACK=none      # or: evalcascade run ... --policy jev
```

**Stricter escalation for one metric**

```toml
[policy.overrides.groundedness]
escalate_below = 0.9
```

**A CI job with a throwaway workspace**

```bash
export EVALCASCADE_DISABLE_DOTENV=1
export EVALCASCADE_HOME="$RUNNER_TEMP/evalcascade"
```

## Python

```python
from evalcascade import Settings, EvalSuite
from evalcascade.metrics import Groundedness

settings = Settings.load()  # defaults + toml + env (+ .env)
settings = Settings.load("ci/evalcascade.toml", judge={"model": "openai/gpt-4.1"})
suite = EvalSuite([Groundedness(granularity="sentence")], settings=settings)
```

Keyword arguments to `Settings.load` override everything else. `Settings.load(env={})`
ignores the process environment and `.env`, which is useful in tests. In Python, the
metrics you construct yourself are used as given. `[metrics.<name>]` parameters are only
applied when metrics are built by name, as in `evalcascade.metrics.build_metrics(names,
settings.metrics)`.
