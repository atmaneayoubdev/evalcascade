# Contributing to EvalCascade

Thanks for helping improve EvalCascade. This guide covers the development setup, the
checks every change must pass, and how to add a metric or an evaluator backend.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md). Please
report security problems privately, as described in [SECURITY.md](SECURITY.md), not in
public issues.

## Development setup

Prerequisites:

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 and npm (only if you work on the dashboard in `web/`)
- Docker (optional, for the container image)

```bash
git clone https://github.com/atmaneayoubdev/evalcascade.git
cd evalcascade
uv sync                          # creates .venv with the package (editable) and dev tools
uv run pre-commit install        # ruff, whitespace, YAML/TOML checks, secret guards
uv run evalcascade --help
```

For live provider access, copy the template and add your own key:

```bash
cp .env.example .env             # git-ignored; never commit it
```

You don't need a key for development. The test suite runs fully offline, and
`uv run evalcascade demo` or `--policy deterministic` work without one.

## Running the checks

CI runs all of these. Run them locally before you open a pull request:

```bash
uv run pytest                                   # unit + CLI/API tests (offline)
uv run pytest --cov=evalcascade                 # with coverage
uv run ruff check .                             # lint (add --fix for safe autofixes)
uv run ruff format .                            # format (CI runs: ruff format --check .)
uv run mypy                                     # strict type checking of src/evalcascade
uv build                                        # sdist + wheel
uv run pre-commit run --all-files               # everything the git hook runs
```

Dashboard checks (from `web/`): `npm ci`, `npm run lint`, `npm run typecheck`,
`npm run build`.

### Test rules

- **Tests never touch the network.** Mock HTTP with [`respx`](https://lundberg.github.io/respx/),
  or use a scripted evaluator (see `ScriptedEvaluator` in `tests/conftest.py`).
- An autouse fixture in `tests/conftest.py` removes every `OPENROUTER_*`, `EVALCASCADE_*`
  and `QWEN_*` variable, sets `EVALCASCADE_DISABLE_DOTENV=1`, points `EVALCASCADE_HOME` at
  a temporary directory and runs each test in a clean working directory. Don't bypass it.
- Use obviously fake credentials assembled at runtime (see `FAKE_KEY` in `conftest.py`).
  Don't paste anything that looks like a real key into a test.

### Live tests (opt-in)

Tests that call real provider APIs are marked `@pytest.mark.live`. They are skipped unless
you opt in explicitly. They spend real credits and never run in CI.

```bash
EVALCASCADE_LIVE_TESTS=1 uv run pytest -m live
```

They read `OPENROUTER_API_KEY` (and any judge settings) from your environment. Keep live
tests small, with one or two cases and cheap models.

### Working on the dashboard

```bash
uv run evalcascade demo                                  # seed clearly-labelled demo data
uv run evalcascade serve                                 # API on http://127.0.0.1:8000
cd web && npm ci
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 npm run dev   # dashboard on http://localhost:3000
```

The API allows CORS from `localhost:3000` by default. To bundle the dashboard into the
Python package (`src/evalcascade/dashboard_dist/`, git-ignored), run:

```bash
uv run python scripts/build_dashboard.py                 # npm ci + npm run build + copy
uv run python scripts/build_dashboard.py --skip-build    # copy an existing web/out only
```

## Project layout

```text
src/evalcascade/
  core/         metric, rubric (typed questions), evaluator base, policy, cascade runtime, suite
  metrics/      the 13 built-in metrics (general.py, rag.py, agent.py) + registry and suites
  evaluators/   deterministic, jev (System One), llm_judge (OpenAI-compatible), simulated (demo)
  providers/    HTTP client (timeouts, retries, redaction), Jev Decisions client, chat client
  datasets/     JSONL datasets and bundled sample datasets
  experiments/  experiment records, summaries, comparisons
  regression/   CI regression gate
  storage/      SQLite persistence (SQLAlchemy)
  api/          FastAPI app served by `evalcascade serve`
  cli/          Typer CLI
web/            Next.js dashboard (static export)
docs/           reference documentation and the API contract (api-contract.ts)
```

## Adding a metric

A metric describes **what** is judged. It never decides **who** judges it. It can provide
a deterministic `check()`, a provider-independent `rubric()` of typed questions, or both.
The runtime and policy pick the evaluator.

1. **Subclass `Metric`** in the matching module (`metrics/general.py`, `metrics/rag.py`
   or `metrics/agent.py`). Set the class metadata: `name`, `display_name`, `category`,
   `description`, `primitives`, `deterministic_support`, `required_fields`,
   `optional_fields` and `default_threshold`.
2. **Implement `check()`** when code can decide the outcome, such as an exact match, a
   schema check or a count. Return a `DeterministicOutcome` with a score in `[0, 1]`, or
   `None` to defer to semantic judgment.
3. **Implement `rubric()`** for semantic judgment. Use `BinaryQuestion`, `ChoiceQuestion`
   or `ScoreQuestion`. Question ids must match `^[A-Za-z][A-Za-z0-9_]{0,63}$`. Score
   scales have 2 to 10 levels, with the worst level first. Build the state with
   `base_state(request)` so shared keys (`user_input`, `response`) stay identical across
   metrics and Jev can batch them into one request. Keep aggregation-only data in
   `Rubric.aux`, which is never sent to an evaluator.
4. **Override `aggregate()`** if a plain weighted mean of the answer scores is not the
   right combination. Put per-item details (for example `details["steps"]` for agent
   metrics) in the returned `Aggregation`.
5. **Register the metric** in `METRICS` in `metrics/__init__.py`, and add it to a bundle in
   `SUITES` if it belongs there.
6. **Test it:** the deterministic path, the rubric shape (question ids, state keys), the
   aggregation, and the skipped / not-applicable cases. Use a scripted evaluator; don't
   make network calls.
7. **Document it** in `docs/metrics.md` and add a line to `CHANGELOG.md`.

```python
from evalcascade.core.metric import DeterministicOutcome, Metric
from evalcascade.core.rubric import BinaryQuestion, Rubric
from evalcascade.core.types import EvaluationRequest
from evalcascade.metrics.general import base_state


class Politeness(Metric):
    name = "politeness"
    display_name = "Politeness"
    category = "general"
    description = "Whether the response is polite and respectful."
    primitives = ("binary",)
    deterministic_support = "partial"
    required_fields = ("output",)
    default_threshold = 0.5

    def check(self, request: EvaluationRequest) -> DeterministicOutcome | None:
        if not (request.output or "").strip():
            return DeterministicOutcome(score=0.0, explanation="The response is empty.")
        return None  # defer to semantic judgment

    def rubric(self, request: EvaluationRequest) -> Rubric:
        return Rubric(
            questions=[
                BinaryQuestion(
                    id="polite",
                    instructions="Is `response` polite and respectful toward the user?",
                    true="Polite and respectful.",
                    false="Rude, dismissive or disrespectful.",
                )
            ],
            state=base_state(request),
        )
```

## Adding an evaluator backend

An evaluator decides **how** a rubric gets answered. Most backends only need to answer
typed questions. Scoring, confidence handling and error handling are shared.

1. **Subclass `SemanticEvaluator`** (`evalcascade.core.evaluator`) and implement
   `async answer(rubric) -> RawAnswers`. Build each answer with the helpers in
   `evalcascade.core.rubric` (`answer_binary`, `answer_choice`, `answer_score`) so scores
   are normalized to `[0, 1]` the same way for every backend. Set `confidence_source`
   honestly (`provider`, `derived` or `self_reported`).
2. **Set `kind`** (`system_one` or `llm_judge`) **and `route_label`** (`jev` for a fast
   System One-style judge, `llm` for a generative judge). Routing statistics depend on them.
3. **Handle failures by raising `EvalCascadeError` subclasses**, such as `ProviderError`
   or `ResponseValidationError`. `SemanticEvaluator.evaluate()` turns them into error
   judgments, which the cascade can escalate. Don't let other exceptions escape.
4. **Keep secrets safe:** accept keys as `SecretStr`, and send HTTP through
   `evalcascade.providers.http.HTTPClient`. It provides timeouts, bounded retries,
   `Retry-After` support and redacted error messages. `describe()` must never include
   secrets. `available()` should report a missing key so `preflight()` fails fast.
   Release clients in `aclose()`.
5. **Report cost truthfully:** set `cost_source="provider"` when the API returns a cost,
   `estimated` when you compute it from configured prices, and `unknown` when you can't
   tell. Never report a guess as a provider cost.
6. **Test it** with `respx`-mocked HTTP, including the retry, timeout, invalid-response
   and missing-key paths.

Custom evaluators can be passed to a suite in Python right away:
`EvaluationSuite(metrics, evaluators={"mine": MyEvaluator()}, policy=EvaluationPolicy(primary="jev", fallback="mine"))`.
To ship one as a **built-in**, also add:

- a settings model in `config.py`, with environment variables in `_ENV_MAP`,
- the name in `EvaluatorRegistry.get()` and `BUILTIN_EVALUATORS`,
- documentation in `docs/providers.md` and `docs/configuration.md`.

See [docs/providers.md](docs/providers.md#writing-a-custom-evaluator) for a complete
example.

## Commit style

We use [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<optional scope>): <imperative summary, lower case, no trailing period>

<optional body: what and why, wrapped at ~72 characters>

<optional footers: Fixes #123, BREAKING CHANGE: ...>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`.
Typical scopes are `metrics`, `evaluators`, `providers`, `cli`, `api`, `web`, `storage`,
`gate` and `docs`. Examples:

```text
feat(metrics): add sentence-level groundedness
fix(providers): honour Retry-After on 529 responses
docs(cli): document gate exit codes
```

Keep each commit focused on one logical change. Mark breaking changes with `!` after the
type or scope, or with a `BREAKING CHANGE:` footer.

## Pull request checklist

- [ ] The change is focused. Unrelated refactors belong in separate PRs.
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` and
      `uv run mypy` pass locally.
- [ ] New behaviour has tests, and the tests make no network calls.
- [ ] Public behaviour changes are documented (`docs/`, CLI help texts, `README.md`).
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`.
- [ ] No secrets, `.env` files, local databases (`.evalcascade/`) or build output
      (`web/out/`, `dashboard_dist/`) are committed.
- [ ] Dashboard changes pass `npm run lint`, `npm run typecheck` and `npm run build`.
- [ ] Demo or simulated data stays clearly labelled as such.
