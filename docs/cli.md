# CLI reference

```text
evalcascade [--config PATH] [--version] COMMAND [ARGS]...
```

| Command | Purpose |
| --- | --- |
| [`init`](#evalcascade-init) | Create `evalcascade.toml`, a local workspace and the sample datasets |
| [`demo`](#evalcascade-demo) | Seed (or clear) clearly-labelled demonstration experiments |
| [`doctor`](#evalcascade-doctor) | Check the environment, configuration, database and provider connectivity |
| [`evaluate`](#evalcascade-evaluate) | Evaluate a single interaction |
| [`run`](#evalcascade-run) | Run a metric suite over a dataset and record the experiment |
| [`datasets`](#evalcascade-datasets) | `list`, `import`, `create`, `show`, `validate` |
| [`experiments`](#evalcascade-experiments) | `list`, `show`, `export`, `import`, `delete` |
| [`compare`](#evalcascade-compare) | Compare two experiments |
| [`gate`](#evalcascade-gate) | Fail (exit 1) when a candidate regresses against a baseline |
| [`metrics`](#evalcascade-metrics) | List the available metrics and suites |
| [`serve`](#evalcascade-serve) | Start the local API and dashboard |

## Global options

| Option | Description |
| --- | --- |
| `--config`, `-c PATH` | Path to `evalcascade.toml`. Env: `EVALCASCADE_CONFIG`. Default: `./evalcascade.toml` if present. |
| `--version` | Print the version and exit. |
| `--install-completion` / `--show-completion` | Shell completion helpers (Typer). |
| `--help` | Show help. Works on every command. |

Global options go **before** the command: `evalcascade -c ci/evalcascade.toml run ...`.
The `gate` command uses `-c` for `--candidate`. That is a separate option on the
subcommand.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success (for `gate`: no regression) |
| `1` | `gate` found a regression; `doctor` found a hard failure; `datasets validate` found an invalid file; `experiments delete` was declined |
| `2` | Usage or configuration error: bad option, missing API key for the chosen policy, dataset or experiment not found, invalid file |

## Experiment and dataset references

Commands that take an **experiment** accept:

- a full id (`76e103bad6dc`) or a unique id prefix (`76e1`),
- an experiment name, which resolves to the most recent experiment with that name,
- `latest` (the newest experiment) or `latest~N` (N experiments before it),
- for `experiments show`, `compare` and `gate`: a path to an exported `.json` file.

Commands that take a **dataset** accept a JSONL/JSON file path, the name of a registered
dataset, or `sample:<name>` for a bundled sample (`sample:rag_qa`, `sample:agent_tasks`,
`sample:support_bot`). See [datasets.md](datasets.md).

## Metric selection and policies

`evaluate` and `run` share these options:

| Option | Description |
| --- | --- |
| `--metric`, `-m NAME` | Metric to evaluate (repeatable). See [metrics.md](metrics.md). |
| `--suite`, `-s NAME` | Metric bundle (repeatable): `general`, `rag`, `agent`. |
| `--policy`, `-p NAME` | Policy preset: `cascade`, `jev`, `llm`, `deterministic`. |
| `--escalate-below FLOAT` | Escalation threshold in `[0, 1]` (default `0.82`). |

- `--metric` and `--suite` combine. Suites expand to their metrics and duplicates are
  dropped.
- With neither option, a default suite is chosen from the data: `agent` if there is a trace,
  otherwise `rag` if there is context, otherwise `general`.
- Per-metric parameters from `[metrics.<name>]` in `evalcascade.toml` are applied.

| Preset | Behaviour | Keys needed |
| --- | --- | --- |
| `cascade` | deterministic → Jev → LLM judge on low confidence or Jev error | `OPENROUTER_API_KEY` (+ judge key if not OpenRouter) |
| `jev` | deterministic → Jev; never calls an LLM judge | `OPENROUTER_API_KEY` |
| `llm` | deterministic → LLM judge for everything semantic | judge key |
| `deterministic` | deterministic checks only; semantic metrics are skipped | none |

Without `--policy`, the `[policy]` configuration applies (default: the cascade), and
`--escalate-below` overrides its threshold. `--policy` **replaces** the configured policy,
including any `[policy.overrides]`. Before evaluating, the CLI checks that every evaluator
the policy needs has a key. If one is missing it exits with code `2` without making any
request.

---

## `evalcascade init`

```text
evalcascade init [DIRECTORY] [--demo] [--force]
```

Sets up a project in `DIRECTORY` (default `.`):

- writes `evalcascade.toml` from a commented template (kept if it exists, unless `--force`),
- creates the workspace (`.evalcascade/`, with the SQLite database),
- copies the three sample datasets to `datasets/` and registers them,
- appends `.evalcascade/` and `.env` to `.gitignore`.

| Option | Description |
| --- | --- |
| `--demo` | Also seed the demonstration experiments (see `demo`). |
| `--force` | Overwrite an existing `evalcascade.toml`. |

```bash
evalcascade init
evalcascade init my-evals --demo
```

## `evalcascade demo`

```text
evalcascade demo [--clear]
```

Seeds six **demonstration** experiments (`support-bot`, `rag-assistant` ×3,
`agent-planner` ×2) with the simulated evaluator, so the dashboard has data before you
run a real evaluation. It makes no API calls. Demo experiments are flagged `is_demo` and
labelled `DEMO` in the CLI, the API and the dashboard. Running `demo` again replaces them.

| Option | Description |
| --- | --- |
| `--clear` | Remove all demo experiments instead. |

## `evalcascade doctor`

```text
evalcascade doctor [--live]
```

Prints a checklist:

- Python version (3.12 or newer) and EvalCascade version,
- configuration file, database connectivity, and experiment and dataset counts,
- whether `OPENROUTER_API_KEY` and the judge key are set (values are never shown),
- the judge provider, model and base URL, and the active policy,
- whether a dashboard bundle was found.

When `OPENROUTER_API_KEY` is set, `doctor` also calls OpenRouter's key endpoint
(`GET {jev.base_url}/v1/key`) to verify it, and shows the remaining credit when OpenRouter
reports one. This check is free.

| Option | Description |
| --- | --- |
| `--live` | Also send one tiny Jev decision and one LLM-judge request (costs well under $0.001). |

Exits `1` on a hard failure: Python too old, invalid configuration, or database unreachable.
Missing keys are warnings.

## `evalcascade evaluate`

```text
evalcascade evaluate [OPTIONS]
```

Evaluates one interaction and prints a result panel with each metric's score, verdict,
route, confidence (`primary → final` when escalated), latency and cost.

| Option | Description |
| --- | --- |
| `--input`, `-i TEXT` | User input / prompt. |
| `--output`, `-o TEXT` | The system output to evaluate (text, not a file). |
| `--context TEXT` | A retrieved passage (repeatable; order matters for `[n]` citations). |
| `--expected`, `-e TEXT` | Reference answer (sets `expected.answer`). |
| `--trace PATH` | JSON file with an agent trace (`{"steps": [...], "tools": [...]}`). |
| `--metric`, `-m` / `--suite`, `-s` / `--policy`, `-p` / `--escalate-below` | See [Metric selection](#metric-selection-and-policies). |
| `--json` | Print the full `EvaluationResult` as JSON. |

```bash
evalcascade evaluate -i "What is 2 + 2?" -o "4" -e "4" -m correctness --policy deterministic
evalcascade evaluate -i "How long are backups kept?" \
  -o "Backups are kept for 30 days [1]." \
  --context "Automated backups are retained for 30 days." --suite rag
evalcascade evaluate -i "Weather in Oslo?" -o "4°C and cloudy." --trace trace.json --json
```

## `evalcascade run`

```text
evalcascade run DATASET [OPTIONS]
```

Evaluates every case of `DATASET` (a path, registered name or `sample:<name>`), prints the
experiment summary and records the experiment in the database.

| Option | Description |
| --- | --- |
| `--metric`, `-m` / `--suite`, `-s` / `--policy`, `-p` / `--escalate-below` | See [Metric selection](#metric-selection-and-policies). |
| `--name`, `-n TEXT` | Experiment name, for example `baseline` or `candidate`. Default: `<dataset>-run`. |
| `--tag TEXT` | Tag (repeatable). |
| `--notes TEXT` | Free-text notes. |
| `--concurrency INT` | Cases evaluated in parallel, 1-64. Default `8`. |
| `--limit INT` | Only evaluate the first N cases. |
| `--save` / `--no-save` | Record the experiment in the database. Default: save. |
| `--output`, `-o PATH` | Also export the experiment as JSON, for example as a CI baseline. |

In `run`, `-o` is an export **path**. In `evaluate`, `-o` is the output **text**.

```bash
evalcascade run datasets/rag_qa.jsonl --suite rag --name baseline
evalcascade run sample:agent_tasks --suite agent --policy jev --limit 3
evalcascade run sample:rag_qa --suite rag --policy deterministic --no-save -o out.json
```

The summary shows the overall score, pass rate, Jev acceptance rate, escalation rate,
deterministic share, latency p50/p95 and cost. A `*` after the cost means some calls
reported no cost. It also has a per-metric table with the routes taken (Det / Jev /
Jev→LLM / LLM) and the skipped/error counts.

## `evalcascade datasets`

### `datasets list`

Lists registered datasets with case counts, field coverage, content hash and path.

### `datasets import`

```text
evalcascade datasets import PATH [--name TEXT] [--description TEXT] [--force]
```

Validates a `.jsonl` (or `.json` list) file and registers it. The file is copied to
`<home>/datasets/<name>.jsonl`.

| Option | Description |
| --- | --- |
| `--name TEXT` | Dataset name. Default: the file stem. |
| `--description TEXT` | Description. |
| `--force` | Replace an existing dataset with the same name. |

### `datasets create`

```text
evalcascade datasets create NAME [--template general|rag|agent] [--output PATH]
```

Writes a starter file from a template (default `general`) to `datasets/<NAME>.jsonl`, or
to `--output`/`-o`, and registers it in place. It refuses to overwrite an existing file.

### `datasets show`

```text
evalcascade datasets show DATASET [--limit N]
```

Prints size, content hash, field coverage and a preview of the first `N` cases
(`--limit`/`-n`, default `5`).

### `datasets validate`

```text
evalcascade datasets validate PATH
```

Validates a file without registering it. Prints the case count and field coverage, or the
line-numbered errors (exit code `1`).

## `evalcascade experiments`

### `experiments list`

```text
evalcascade experiments list [--limit N] [--demo/--no-demo] [--name TEXT]
```

Lists experiments, newest first. Default `--limit`/`-n` is `20`; `--no-demo` hides demo
experiments; `--name` filters by exact name.

### `experiments show`

```text
evalcascade experiments show REF [--cases] [--case CASE_ID]
```

Shows the experiment summary, dataset hash, creation time and evaluator models. `REF` may
also be an exported `.json` file.

| Option | Description |
| --- | --- |
| `--cases` | Also list per-case results (score, verdict, escalations, latency, cost). |
| `--case CASE_ID` | Show one case in detail, with the full per-metric result panel. |

### `experiments export`

```text
evalcascade experiments export REF --output PATH
```

Writes a self-contained JSON export: summary, per-case results, metric configuration,
policy and evaluator descriptions. It contains no secrets. `--output`/`-o` is required. This
is how you create CI baselines (see [examples/ci](../examples/ci/README.md)).

### `experiments import`

```text
evalcascade experiments import PATH
```

Imports an export into the local database, for example to view a CI artifact in the
dashboard. It fails if an experiment with the same id already exists.

### `experiments delete`

```text
evalcascade experiments delete REF [--yes]
```

Deletes an experiment and its case results. It asks for confirmation unless `--yes`/`-y`
is given.

## `evalcascade compare`

```text
evalcascade compare BASELINE CANDIDATE [--json]
```

Compares two experiments (references or `.json` exports). It reports:

- deltas in overall score, pass rate, Jev acceptance rate, escalation rate, total cost,
  cost per case and latency p50/p95,
- per-metric mean deltas,
- case-level counts: matched, improved, regressed and unchanged cases (±0.01 tolerance on
  the case's overall score), and cases found in only one experiment.

It warns when the two experiments used datasets with different content hashes. `--json`
prints the full `Comparison` object.

```bash
evalcascade compare baseline candidate
evalcascade compare evals/baseline.json latest --json
```

## `evalcascade gate`

```text
evalcascade gate --baseline REF [--candidate REF] [OPTIONS]
```

Compares a candidate with a baseline and exits `1` if any check fails. Drops are absolute
on the 0-1 score scale: `0.03` means 3 points.

| Option | Default | Description |
| --- | --- | --- |
| `--baseline`, `-b REF` | required | Baseline experiment (reference or `.json`). |
| `--candidate`, `-c REF` | `latest` | Candidate experiment (reference or `.json`). |
| `--max-quality-drop FLOAT` | `0.03` | Maximum drop of the overall score. |
| `--metric-threshold NAME=FLOAT` | none | Maximum drop for one metric (repeatable). A listed metric that is missing from the candidate fails. |
| `--max-metric-drop FLOAT` | none | Default maximum drop for every metric that has no `--metric-threshold`. |
| `--max-cost-increase FLOAT` | none | Maximum relative increase in total cost (`0.2` = +20 %). |
| `--max-latency-increase FLOAT` | none | Maximum relative increase in p95 case latency. |
| `--min-score FLOAT` | none | Minimum candidate overall score. |
| `--max-escalation-rate FLOAT` | none | Maximum candidate escalation rate (escalations / Jev attempts). |
| `--require-same-dataset` | off | Fail if the dataset content hashes differ. |
| `--format`, `-f TEXT` | `text` | `text` (tables), `json` (`GateResult`) or `markdown`. |
| `--summary-file PATH` | none | Append the Markdown report to this file, for example `$GITHUB_STEP_SUMMARY`. |

- The overall-score check fails if either experiment has no overall score.
- A metric check fails if the metric has a baseline score but none in the candidate. It
  passes, reported as a new metric, if there is no baseline score.
- A cost or latency check against a zero baseline passes only if the candidate is also zero.
- With two `.json` files, `gate` is fully offline: it needs no API key and no database.

```bash
evalcascade gate -b evals/baseline.json -c candidate.json --max-quality-drop 0.03 \
  --metric-threshold groundedness=0.05 --summary-file "$GITHUB_STEP_SUMMARY"
evalcascade gate -b baseline --max-cost-increase 0.2 --min-score 0.75 --format markdown
```

## `evalcascade metrics`

Lists every metric with its category, judgment primitives, deterministic support, required
fields and description, followed by the suite definitions. See [metrics.md](metrics.md).

## `evalcascade serve`

```text
evalcascade serve [--host HOST] [--port PORT] [--reload]
```

Starts the FastAPI server: the API under `/api`, OpenAPI docs at `/docs`, and the dashboard
at `/` when a bundle is found.

| Option | Default | Description |
| --- | --- | --- |
| `--host TEXT` | `127.0.0.1` | Bind address. |
| `--port INT` | `8000` | Port. |
| `--reload` | off | Auto-reload on code changes (development). |

Binding to anything other than `127.0.0.1`, `localhost` or `::1` without
`EVALCASCADE_API_TOKEN` prints a warning, because anyone who can reach the port could run
evaluations billed to your keys. See [api.md](api.md#authentication).

The dashboard bundle is looked up in this order:

1. `$EVALCASCADE_DASHBOARD_DIR`
2. the copy packaged in the wheel (`evalcascade/dashboard_dist`)
3. `./web/out`
4. the repository's `web/out` (editable installs)

Build it with `python scripts/build_dashboard.py`.
