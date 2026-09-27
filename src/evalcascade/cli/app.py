"""The ``evalcascade`` command-line interface."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from evalcascade._version import __version__
from evalcascade.cli import render
from evalcascade.config import CONFIG_FILENAME, Settings
from evalcascade.core.policy import EvaluationPolicy
from evalcascade.core.results import CaseResult
from evalcascade.errors import EvalCascadeError
from evalcascade.experiments.experiment import Experiment

app = typer.Typer(
    name="evalcascade",
    help="Adaptive evaluation for LLM, RAG and agentic systems. "
    "System One judges first, LLMs only when necessary.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)
datasets_app = typer.Typer(help="Create, import and inspect datasets.", no_args_is_help=True)
experiments_app = typer.Typer(help="List, inspect, export and delete experiments.", no_args_is_help=True)
app.add_typer(datasets_app, name="datasets")
app.add_typer(experiments_app, name="experiments")

console = render.make_console()
err_console = Console(stderr=True, highlight=False)


class State:
    config: Path | None = None
    _settings: Settings | None = None

    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = Settings.load(self.config)
        return self._settings

    def store(self) -> Any:
        from evalcascade.storage.store import ExperimentStore

        return ExperimentStore.from_settings(self.settings())


state = State()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"evalcascade {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help=f"Path to {CONFIG_FILENAME}.", envvar="EVALCASCADE_CONFIG")
    ] = None,
    version: Annotated[
        bool, typer.Option("--version", callback=_version_callback, is_eager=True, help="Show the version.")
    ] = False,
) -> None:
    state.config = config
    state._settings = None


def fail(message: str, code: int = 2) -> typer.Exit:
    err_console.print(Text(f"error: {message}", style="red"))
    return typer.Exit(code)


# ---------------------------------------------------------------------------
# init / demo / doctor
# ---------------------------------------------------------------------------

CONFIG_TEMPLATE = """\
# EvalCascade project configuration.
# API keys belong in the environment (.env), never in this file.

[evalcascade]
home = ".evalcascade"          # local workspace: SQLite database + imported datasets

[policy]
deterministic_first = true
primary = "jev"                # System One judge (TypeSafe Jev via OpenRouter)
fallback = "llm"               # generative judge used on escalation
escalate_below = 0.82          # escalate when Jev confidence is below this

[jev]
model = "typesafe/jev-1.13"
surface = "decisions"          # "decisions" (POST /api/alpha/decisions) or "systemone"
timeout_s = 30

[judge]
provider = "openrouter"        # or "openai_compatible" + EVALCASCADE_JUDGE_BASE_URL
model = "openai/gpt-4.1-mini"
temperature = 0.0

# Per-metric parameters, e.g.:
# [metrics.groundedness]
# threshold = 0.7
# escalate_below = 0.9
# granularity = "sentence"
"""


@app.command()
def init(
    directory: Annotated[Path, typer.Argument(help="Project directory.")] = Path("."),
    demo: Annotated[bool, typer.Option("--demo", help="Also seed demonstration experiments.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing evalcascade.toml.")] = False,
) -> None:
    """Create evalcascade.toml, a local workspace and sample datasets."""
    from evalcascade.datasets import SAMPLE_DATASETS, sample_path
    from evalcascade.storage.store import ExperimentStore

    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / CONFIG_FILENAME
    if config_path.exists() and not force:
        console.print(f"[dim]keeping existing[/dim] {config_path}")
    else:
        config_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        console.print(f"[green]created[/green] {config_path}")

    settings = Settings.load(config_path)
    store = ExperimentStore.from_settings(settings)
    data_dir = directory / "datasets"
    data_dir.mkdir(exist_ok=True)
    from evalcascade.datasets import Dataset

    for name in SAMPLE_DATASETS:
        target = data_dir / f"{name}.jsonl"
        if not target.exists():
            shutil.copyfile(sample_path(name), target)
        store.register_dataset(Dataset.from_jsonl(target, name=name), copy_to_workspace=False, overwrite=True)
    console.print(f"[green]added[/green] sample datasets to {data_dir}")
    console.print(f"[green]database[/green] {settings.resolved_database_url}")

    gitignore = directory / ".gitignore"
    lines = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [p for p in (".evalcascade/", ".env") if p not in lines]
    if missing:
        with gitignore.open("a", encoding="utf-8") as fh:
            fh.write(("\n" if lines and lines[-1] else "") + "\n".join(missing) + "\n")
        console.print(f"[green]updated[/green] .gitignore ({', '.join(missing)})")

    if demo:
        from evalcascade.demo import seed_demo

        created = seed_demo(store)
        console.print(f"[yellow]seeded {len(created)} DEMO experiments[/yellow] (simulated, not real results)")
    store.dispose()
    console.print(
        "\nNext steps:\n"
        "  1. export OPENROUTER_API_KEY=...        (or put it in .env)\n"
        "  2. evalcascade doctor\n"
        "  3. evalcascade run datasets/rag_qa.jsonl --suite rag --name baseline\n"
        "  4. evalcascade serve                    (dashboard at http://127.0.0.1:8000)"
    )


@app.command()
def demo(
    clear: Annotated[bool, typer.Option("--clear", help="Remove demo experiments instead.")] = False,
) -> None:
    """Seed (or clear) demonstration experiments. No API calls; clearly marked DEMO."""
    from evalcascade.demo import seed_demo

    store = state.store()
    if clear:
        n = store.delete_demo_experiments()
        console.print(f"removed {n} demo experiment(s)")
        return
    created = seed_demo(store)
    console.print(
        f"[yellow]Seeded {len(created)} DEMO experiments[/yellow] using the simulated evaluator. "
        "They are labelled DEMO everywhere and are not real evaluation results."
    )
    console.print(render.experiments_table(store.list_experiments(limit=len(created))))


@app.command()
def doctor(
    live: Annotated[
        bool, typer.Option("--live", help="Also send one tiny Jev decision and one judge request (costs < $0.001).")
    ] = False,
) -> None:
    """Check the environment, database, configuration and provider connectivity."""
    rows: list[tuple[str, str, str]] = []  # (status, check, details)
    hard_fail = False

    py_ok = sys.version_info >= (3, 12)
    rows.append(("ok" if py_ok else "fail", "Python", f"{platform.python_version()} ({sys.executable})"))
    hard_fail |= not py_ok
    rows.append(("ok", "EvalCascade", __version__))

    try:
        settings = state.settings()
    except EvalCascadeError as exc:
        rows.append(("fail", "Configuration", str(exc)))
        _doctor_table(rows)
        raise typer.Exit(1) from None
    rows.append(("ok", "Configuration", str(settings.config_file) if settings.config_file else "defaults + environment"))

    try:
        store = state.store()
        ok = store.ping()
        n_exp, n_ds = store.count_experiments(), len(store.list_datasets())
        rows.append(("ok" if ok else "fail", "Database", f"{settings.resolved_database_url} ({n_exp} experiments, {n_ds} datasets)"))
        hard_fail |= not ok
    except Exception as exc:
        rows.append(("fail", "Database", f"{type(exc).__name__}: {exc}"))
        hard_fail = True

    key_set = settings.openrouter_api_key is not None
    rows.append(("ok" if key_set else "warn", "OPENROUTER_API_KEY", "set (value hidden)" if key_set else "not set — Jev is unavailable; deterministic metrics still work"))
    judge_key = settings.judge_api_key() is not None
    rows.append(("ok" if judge_key else "warn", "LLM judge", f"{settings.judge.provider} · {settings.judge.model} · {settings.judge.base_url} · key {'set' if judge_key else 'NOT set'}"))
    rows.append(("ok", "Policy", f"primary={settings.policy.primary} fallback={settings.policy.fallback} escalate_below={settings.policy.escalate_below}"))

    if key_set:
        rows.append(asyncio.run(_check_openrouter_key(settings)))
    if live:
        rows.extend(asyncio.run(_live_checks(settings, jev=key_set, judge=judge_key)))

    from evalcascade.api.static import find_dashboard

    dash = find_dashboard()
    rows.append(("ok" if dash else "warn", "Dashboard bundle", str(dash) if dash else "not built — API only (build with: python scripts/build_dashboard.py)"))
    _doctor_table(rows)
    if hard_fail:
        raise typer.Exit(1)


def _doctor_table(rows: list[tuple[str, str, str]]) -> None:
    style = {"ok": ("✓", "green"), "warn": ("!", "yellow"), "fail": ("✗", "red")}
    table = Table(header_style="bold", title="evalcascade doctor", title_justify="left")
    table.add_column("")
    table.add_column("Check")
    table.add_column("Details", overflow="fold")
    for status, check, details in rows:
        icon, color = style[status]
        table.add_row(Text(icon, style=color), check, details)
    console.print(table)


async def _check_openrouter_key(settings: Settings) -> tuple[str, str, str]:
    from evalcascade.providers.http import HTTPClient, RetryPolicy

    client = HTTPClient(
        provider="openrouter",
        base_url=f"{settings.jev.base_url.rstrip('/')}/v1",
        api_key=settings.openrouter_api_key,
        timeout_s=15,
        retry=RetryPolicy(max_retries=1),
    )
    try:
        response = await client.get_json("/key")
        data = response.data.get("data", {}) if isinstance(response.data.get("data"), dict) else {}
        limit = data.get("limit_remaining")
        extra = f", credit remaining ${limit:.2f}" if isinstance(limit, int | float) else ""
        return ("ok", "OpenRouter connectivity", f"authenticated ({response.latency_ms:.0f} ms{extra})")
    except EvalCascadeError as exc:
        return ("fail", "OpenRouter connectivity", str(exc))
    finally:
        await client.aclose()


async def _live_checks(settings: Settings, *, jev: bool, judge: bool) -> list[tuple[str, str, str]]:
    from evalcascade.core.types import EvaluationRequest
    from evalcascade.evaluators.jev import JevEvaluator
    from evalcascade.evaluators.llm_judge import LLMJudge
    from evalcascade.metrics import AnswerRelevance

    request = EvaluationRequest(input="What is the capital of France?", output="Paris is the capital of France.")
    metric = AnswerRelevance()
    rows = []
    for enabled, label, evaluator in (
        (jev, "Jev live decision", JevEvaluator.from_settings(settings) if jev else None),
        (judge, "LLM judge live call", LLMJudge.from_settings(settings) if judge else None),
    ):
        if not enabled or evaluator is None:
            continue
        try:
            j = await evaluator.evaluate(metric, request)
        finally:
            await evaluator.aclose()
        if j.error:
            rows.append(("fail", label, j.error))
        else:
            rows.append(("ok", label, f"{j.model} · score {j.score:.2f} · confidence {render.fmt_score(j.confidence, 2)} · {j.latency_ms:.0f} ms · {render.fmt_cost(j.cost_usd, j.cost_source != 'unknown')}"))
    return rows


# ---------------------------------------------------------------------------
# evaluate / run
# ---------------------------------------------------------------------------


def _build_suite(
    metric_names: list[str] | None,
    suite_names: list[str] | None,
    policy_name: str | None,
    escalate_below: float | None,
    default_suite: str = "general",
) -> Any:
    from evalcascade.core.suite import EvaluationSuite
    from evalcascade.metrics import build_metrics

    settings = state.settings()
    names = [*(suite_names or []), *(metric_names or [])] or [default_suite]
    metrics = build_metrics(names, settings.metrics)
    if policy_name:
        policy = EvaluationPolicy.preset(policy_name, escalate_below)
    else:
        policy = settings.policy
        if escalate_below is not None:
            policy = policy.model_copy(update={"escalate_below": escalate_below})
    return EvaluationSuite(metrics, policy=policy, settings=settings)


MetricOpt = Annotated[list[str] | None, typer.Option("--metric", "-m", help="Metric name (repeatable).")]
SuiteOpt = Annotated[list[str] | None, typer.Option("--suite", "-s", help="Metric bundle: general, rag, agent (repeatable).")]
PolicyOpt = Annotated[
    str | None, typer.Option("--policy", "-p", help="cascade (default), jev, llm or deterministic.")
]
EscalateOpt = Annotated[float | None, typer.Option("--escalate-below", min=0.0, max=1.0, help="Escalation threshold.")]


@app.command()
def evaluate(
    input: Annotated[str | None, typer.Option("--input", "-i", help="User input / prompt.")] = None,
    output: Annotated[str | None, typer.Option("--output", "-o", help="System output to evaluate.")] = None,
    context: Annotated[list[str] | None, typer.Option("--context", help="Retrieved passage (repeatable).")] = None,
    expected: Annotated[str | None, typer.Option("--expected", "-e", help="Reference answer.")] = None,
    trace_file: Annotated[Path | None, typer.Option("--trace", help="JSON file with an agent trace.")] = None,
    metric: MetricOpt = None,
    suite: SuiteOpt = None,
    policy: PolicyOpt = None,
    escalate_below: EscalateOpt = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the full result as JSON.")] = False,
) -> None:
    """Evaluate a single interaction."""
    try:
        trace = json.loads(trace_file.read_text(encoding="utf-8")) if trace_file else None
        default = "agent" if trace else "rag" if context else "general"
        evaluation_suite = _build_suite(metric, suite, policy, escalate_below, default_suite=default)
        result = evaluation_suite.evaluate_sync(
            input=input, output=output, context=context, expected=expected, trace=trace
        )
    except (EvalCascadeError, OSError, json.JSONDecodeError) as exc:
        raise fail(str(exc)) from None
    if as_json:
        console.print_json(result.model_dump_json())
    else:
        console.print(render.result_panel(result))


@app.command()
def run(
    dataset: Annotated[str, typer.Argument(help="JSONL path, registered dataset name, or sample:<name>.")],
    metric: MetricOpt = None,
    suite: SuiteOpt = None,
    policy: PolicyOpt = None,
    escalate_below: EscalateOpt = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Experiment name (e.g. baseline).")] = None,
    tag: Annotated[list[str] | None, typer.Option("--tag", help="Tag (repeatable).")] = None,
    notes: Annotated[str | None, typer.Option("--notes", help="Free-text notes.")] = None,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1, max=64, help="Cases evaluated in parallel.")] = 8,
    limit: Annotated[int | None, typer.Option("--limit", min=1, help="Only evaluate the first N cases.")] = None,
    save: Annotated[bool, typer.Option("--save/--no-save", help="Record the experiment in the database.")] = True,
    output_path: Annotated[Path | None, typer.Option("--output", "-o", help="Also export the experiment as JSON.")] = None,
) -> None:
    """Run an evaluation suite over a dataset and record the experiment."""
    from evalcascade.storage.store import resolve_dataset

    try:
        store = state.store() if save else None
        ds = resolve_dataset(dataset, store or state.store())
        default = "agent" if ds.field_coverage()["trace"] else "rag" if ds.field_coverage()["context"] else "general"
        evaluation_suite = _build_suite(metric, suite, policy, escalate_below, default_suite=default)
        evaluation_suite.preflight()
    except EvalCascadeError as exc:
        raise fail(str(exc)) from None

    total = min(len(ds), limit) if limit else len(ds)
    console.print(
        f"Evaluating [bold]{ds.name}[/bold] ({total} cases) with "
        f"{', '.join(m.key for m in evaluation_suite.metrics)} · policy "
        f"primary={evaluation_suite.policy.primary} fallback={evaluation_suite.policy.fallback} "
        f"escalate_below={evaluation_suite.policy.escalate_below}"
    )
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("evaluating", total=total)

        def on_result(_: CaseResult) -> None:
            progress.advance(task_id)

        try:
            experiment = evaluation_suite.run_sync(
                ds,
                name=name,
                concurrency=concurrency,
                limit=limit,
                tags=tag or [],
                notes=notes,
                store=store,
                on_result=on_result,
            )
        except EvalCascadeError as exc:
            raise fail(str(exc)) from None
    console.print(render.experiment_summary(experiment))
    if output_path:
        experiment.to_json(output_path)
        console.print(f"exported to {output_path}")
    if save:
        console.print(f"[dim]saved experiment[/dim] {experiment.id} [dim]({experiment.name})[/dim]")


# ---------------------------------------------------------------------------
# datasets
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "general": [
        {"id": "case-001", "input": "What is the capital of Japan?", "output": "Tokyo.", "expected": {"answer": "Tokyo"}},
        {"id": "case-002", "input": "Write a haiku about rain.", "output": "Soft rain on the roof / ..."},
    ],
    "rag": [
        {
            "id": "case-001",
            "input": "How long are backups kept?",
            "output": "Backups are kept for 30 days [1].",
            "context": ["Automated backups are retained for 30 days."],
            "expected": {"answer": "30 days"},
        }
    ],
    "agent": [
        {
            "id": "case-001",
            "input": "What's the weather in Oslo?",
            "output": "It is 4°C and cloudy in Oslo.",
            "trace": {
                "tools": [{"name": "get_weather", "description": "Weather for a city", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}],
                "steps": [{"type": "tool_call", "tool_call": {"name": "get_weather", "arguments": {"city": "Oslo"}, "result": {"temp": 4, "conditions": "cloudy"}}}],
            },
            "expected": {"tools": ["get_weather"], "max_tool_calls": 1},
        }
    ],
}


@datasets_app.command("list")
def datasets_list() -> None:
    """List registered datasets."""
    items = state.store().list_datasets()
    if not items:
        console.print("No datasets registered. Try: evalcascade init  or  evalcascade datasets import FILE")
        return
    console.print(render.datasets_table(items))


@datasets_app.command("import")
def datasets_import(
    path: Annotated[Path, typer.Argument(help="JSONL (or JSON list) file.")],
    name: Annotated[str | None, typer.Option("--name", help="Dataset name (default: file stem).")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing dataset.")] = False,
) -> None:
    """Validate a dataset file and register it (copied into the workspace)."""
    from evalcascade.datasets import Dataset

    try:
        ds = Dataset.from_jsonl(path, name=name)
        info = state.store().register_dataset(ds, name=name, description=description, overwrite=force)
    except EvalCascadeError as exc:
        raise fail(str(exc)) from None
    console.print(f"[green]imported[/green] {info.name}: {info.num_cases} cases → {info.path}")


@datasets_app.command("create")
def datasets_create(
    name: Annotated[str, typer.Argument(help="Dataset name.")],
    template: Annotated[str, typer.Option("--template", "-t", help="general, rag or agent.")] = "general",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Where to write the JSONL file.")] = None,
) -> None:
    """Create a new dataset from a template and register it."""
    from evalcascade.datasets import Dataset

    if template not in TEMPLATES:
        raise fail(f"unknown template {template!r}; use general, rag or agent")
    target = output or Path("datasets") / f"{name}.jsonl"
    if target.exists():
        raise fail(f"{target} already exists")
    ds = Dataset.from_records(TEMPLATES[template], name=name)
    ds.to_jsonl(target)
    try:
        state.store().register_dataset(Dataset.from_jsonl(target, name=name), copy_to_workspace=False)
    except EvalCascadeError as exc:
        raise fail(str(exc)) from None
    console.print(f"[green]created[/green] {target} ({len(ds)} example case(s)) — edit it, then: evalcascade run {target}")


@datasets_app.command("show")
def datasets_show(
    dataset: Annotated[str, typer.Argument(help="Path, registered name, or sample:<name>.")],
    limit: Annotated[int, typer.Option("--limit", "-n", min=0, help="Cases to preview.")] = 5,
) -> None:
    """Inspect a dataset: size, field coverage and a preview of cases."""
    from evalcascade.storage.store import resolve_dataset

    try:
        ds = resolve_dataset(dataset, state.store())
    except EvalCascadeError as exc:
        raise fail(str(exc)) from None
    coverage = ds.field_coverage()
    console.print(f"[bold]{ds.name}[/bold] · {len(ds)} cases · hash {ds.hash}" + (f" · {ds.path}" if ds.path else ""))
    console.print("fields: " + ", ".join(f"{k} {v}/{len(ds)}" for k, v in coverage.items()))
    table = Table(header_style="bold")
    table.add_column("id")
    table.add_column("input", overflow="fold", max_width=48)
    table.add_column("output", overflow="fold", max_width=48)
    table.add_column("ctx", justify="right")
    table.add_column("trace", justify="right")
    table.add_column("expected", overflow="fold", max_width=30)
    for case in ds.cases[:limit]:
        table.add_row(
            case.id,
            (case.input or "")[:160],
            (case.output or "")[:160],
            str(len(case.context)),
            str(len(case.trace.steps)) if case.trace else "—",
            json.dumps(case.expected.model_dump(exclude_none=True)) if case.expected else "—",
        )
    console.print(table)


@datasets_app.command("validate")
def datasets_validate(path: Annotated[Path, typer.Argument(help="Dataset file.")]) -> None:
    """Validate a dataset file without registering it."""
    from evalcascade.datasets import Dataset

    try:
        ds = Dataset.from_jsonl(path)
    except EvalCascadeError as exc:
        raise fail(str(exc), code=1) from None
    console.print(f"[green]valid[/green] {len(ds)} cases · fields {ds.field_coverage()}")


# ---------------------------------------------------------------------------
# experiments / compare / gate
# ---------------------------------------------------------------------------


def _load_experiment(ref: str) -> Experiment:
    path = Path(ref)
    if path.suffix.lower() == ".json" and path.is_file():
        return Experiment.from_json(path)
    return state.store().get_experiment(ref)  # type: ignore[no-any-return]


@experiments_app.command("list")
def experiments_list(
    limit: Annotated[int, typer.Option("--limit", "-n", min=1)] = 20,
    include_demo: Annotated[bool, typer.Option("--demo/--no-demo", help="Include demo experiments.")] = True,
    name: Annotated[str | None, typer.Option("--name", help="Only experiments with this name.")] = None,
) -> None:
    """List recorded experiments (newest first)."""
    items = state.store().list_experiments(include_demo=include_demo, limit=limit, name=name)
    if not items:
        console.print("No experiments yet. Run: evalcascade run <dataset>  (or evalcascade demo)")
        return
    console.print(render.experiments_table(items))


@experiments_app.command("show")
def experiments_show(
    ref: Annotated[str, typer.Argument(help="Experiment id, prefix, name, latest, or .json export.")],
    cases: Annotated[bool, typer.Option("--cases", help="Also list per-case results.")] = False,
    case_id: Annotated[str | None, typer.Option("--case", help="Show one case in detail.")] = None,
) -> None:
    """Show an experiment's summary (and optionally its cases)."""
    try:
        experiment = _load_experiment(ref)
        if case_id:
            result = experiment.case(case_id)
            console.print(render.result_panel(result))
            return
    except EvalCascadeError as exc:
        raise fail(str(exc)) from None
    console.print(render.experiment_summary(experiment))
    console.print(
        f"[dim]dataset {experiment.dataset.name} ({experiment.dataset.hash}) · created {experiment.created_at:%Y-%m-%d %H:%M} UTC · "
        f"evaluators: {', '.join(f'{k}={v.get('model', v.get('kind'))}' for k, v in experiment.evaluators.items())}[/dim]"
    )
    if cases:
        table = Table(header_style="bold")
        table.add_column("case")
        table.add_column("overall", justify="right")
        table.add_column("result")
        table.add_column("escal.", justify="right")
        table.add_column("latency", justify="right")
        table.add_column("cost", justify="right")
        for r in experiment.results:
            table.add_row(r.case_id or "—", render.fmt_score(r.overall_score), render.pass_text(r.passed), str(r.escalations), render.fmt_ms(r.latency_ms), render.fmt_cost(r.cost_usd))
        console.print(table)


@experiments_app.command("export")
def experiments_export(
    ref: Annotated[str, typer.Argument(help="Experiment reference.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Destination .json file.")],
) -> None:
    """Export an experiment to JSON (e.g. to commit as a CI baseline)."""
    try:
        experiment = state.store().get_experiment(ref)
    except EvalCascadeError as exc:
        raise fail(str(exc)) from None
    experiment.to_json(output)
    console.print(f"exported {experiment.id} ({experiment.name}) → {output}")


@experiments_app.command("import")
def experiments_import(path: Annotated[Path, typer.Argument(help="Experiment .json export.")]) -> None:
    """Import an exported experiment into the local database."""
    try:
        experiment = Experiment.from_json(path)
        state.store().save_experiment(experiment)
    except (EvalCascadeError, ValueError) as exc:
        raise fail(str(exc)) from None
    console.print(f"imported {experiment.id} ({experiment.name})")


@experiments_app.command("delete")
def experiments_delete(
    ref: Annotated[str, typer.Argument(help="Experiment reference.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
) -> None:
    """Delete an experiment."""
    store = state.store()
    try:
        exp_id = store.resolve(ref)
    except EvalCascadeError as exc:
        raise fail(str(exc)) from None
    if not yes and not typer.confirm(f"Delete experiment {exp_id}?"):
        raise typer.Exit(1)
    store.delete_experiment(exp_id)
    console.print(f"deleted {exp_id}")


@app.command()
def compare(
    baseline: Annotated[str, typer.Argument(help="Baseline experiment (ref or .json).")],
    candidate: Annotated[str, typer.Argument(help="Candidate experiment (ref or .json).")],
    as_json: Annotated[bool, typer.Option("--json", help="Print the comparison as JSON.")] = False,
) -> None:
    """Compare two experiments: score, per-metric, cost, latency and routing deltas."""
    from evalcascade.experiments.compare import compare_experiments

    try:
        result = compare_experiments(_load_experiment(baseline), _load_experiment(candidate))
    except EvalCascadeError as exc:
        raise fail(str(exc)) from None
    if as_json:
        console.print_json(result.model_dump_json())
    else:
        console.print(render.comparison_table(result))


def _parse_thresholds(values: list[str] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in values or []:
        if "=" not in item:
            raise fail(f"--metric-threshold expects name=value, got {item!r}")
        key, raw = item.split("=", 1)
        try:
            out[key.strip()] = float(raw)
        except ValueError:
            raise fail(f"invalid threshold value in {item!r}") from None
    return out


@app.command()
def gate(
    baseline: Annotated[str, typer.Option("--baseline", "-b", help="Baseline experiment (ref or .json).")],
    candidate: Annotated[str, typer.Option("--candidate", "-c", help="Candidate experiment (ref or .json).")] = "latest",
    max_quality_drop: Annotated[float, typer.Option("--max-quality-drop", min=0.0, help="Max overall score drop.")] = 0.03,
    metric_threshold: Annotated[
        list[str] | None, typer.Option("--metric-threshold", help="Per-metric max drop, name=value (repeatable).")
    ] = None,
    max_metric_drop: Annotated[float | None, typer.Option("--max-metric-drop", min=0.0, help="Default max drop for every metric.")] = None,
    max_cost_increase: Annotated[float | None, typer.Option("--max-cost-increase", min=0.0, help="Max relative cost increase (0.2 = +20%).")] = None,
    max_latency_increase: Annotated[float | None, typer.Option("--max-latency-increase", min=0.0, help="Max relative p95 latency increase.")] = None,
    min_score: Annotated[float | None, typer.Option("--min-score", min=0.0, max=1.0, help="Minimum candidate overall score.")] = None,
    max_escalation_rate: Annotated[float | None, typer.Option("--max-escalation-rate", min=0.0, max=1.0)] = None,
    require_same_dataset: Annotated[bool, typer.Option("--require-same-dataset", help="Fail if datasets differ.")] = False,
    fmt: Annotated[str, typer.Option("--format", "-f", help="text, json or markdown.")] = "text",
    summary_file: Annotated[
        Path | None, typer.Option("--summary-file", help="Append a markdown report (e.g. $GITHUB_STEP_SUMMARY).")
    ] = None,
) -> None:
    """Fail (exit 1) when the candidate regresses beyond the configured thresholds."""
    from evalcascade.regression.gate import RegressionGate

    try:
        regression_gate = RegressionGate(
            max_quality_drop=max_quality_drop,
            metric_thresholds=_parse_thresholds(metric_threshold),
            max_metric_drop=max_metric_drop,
            max_cost_increase=max_cost_increase,
            max_latency_increase=max_latency_increase,
            min_score=min_score,
            max_escalation_rate=max_escalation_rate,
            require_same_dataset=require_same_dataset,
        )
        result = regression_gate.evaluate(_load_experiment(baseline), _load_experiment(candidate))
    except (EvalCascadeError, ValueError) as exc:
        raise fail(str(exc)) from None
    if fmt == "json":
        console.print_json(result.model_dump_json())
    elif fmt == "markdown":
        console.print(result.to_markdown(), markup=False)
    else:
        console.print(render.comparison_table(result.comparison))
        console.print(render.gate_panel(result))
    if summary_file is not None:
        with summary_file.open("a", encoding="utf-8") as fh:
            fh.write(result.to_markdown())
    raise typer.Exit(0 if result.passed else 1)


# ---------------------------------------------------------------------------
# metrics / serve
# ---------------------------------------------------------------------------


@app.command("metrics")
def metrics_cmd() -> None:
    """List available metrics."""
    from evalcascade.metrics import SUITES, metric_catalog

    table = Table(header_style="bold")
    table.add_column("Metric")
    table.add_column("Category")
    table.add_column("Primitives")
    table.add_column("Deterministic")
    table.add_column("Requires")
    table.add_column("Description", overflow="fold", max_width=70)
    for info in metric_catalog():
        table.add_row(info.name, info.category, ", ".join(info.primitives) or "—", info.deterministic, ", ".join(info.required_fields), info.description)
    console.print(table)
    console.print("[dim]suites: " + "; ".join(f"{k} = {', '.join(v)}" for k, v in SUITES.items()) + "[/dim]")


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port.")] = 8000,
    reload: Annotated[bool, typer.Option("--reload", help="Auto-reload on code changes (development).")] = False,
) -> None:
    """Start the local API and dashboard."""
    import uvicorn

    from evalcascade.api.static import find_dashboard

    if state.config is not None:
        os.environ["EVALCASCADE_CONFIG"] = str(state.config.resolve())
    settings = state.settings()
    if host not in ("127.0.0.1", "localhost", "::1") and settings.api_token is None:
        err_console.print(
            "[yellow]warning:[/yellow] binding to a non-local address without EVALCASCADE_API_TOKEN — "
            "anyone who can reach this port can run evaluations with your API keys."
        )
    dash = find_dashboard()
    console.print(f"EvalCascade API   http://{host}:{port}/api  (OpenAPI docs: http://{host}:{port}/docs)")
    console.print(f"Dashboard         {'http://' + host + ':' + str(port) + '/' if dash else 'not built (API only)'}")
    uvicorn.run("evalcascade.api.app:create_app", factory=True, host=host, port=port, reload=reload, log_level="info")


def main() -> None:
    """Console-script entry point."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - exotic streams
                pass
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
