"""Rich rendering helpers for the CLI."""

from __future__ import annotations

import os
import sys

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from evalcascade.core.results import EvaluationResult
from evalcascade.experiments.compare import Comparison, Delta
from evalcascade.experiments.experiment import Experiment
from evalcascade.regression.gate import GateResult
from evalcascade.storage.store import DatasetInfo, ExperimentListItem

ROUTE_STYLE = {
    "deterministic": "cyan",
    "jev": "green",
    "jev_to_llm": "yellow",
    "llm": "magenta",
    "none": "dim",
}
ROUTE_LABEL = {
    "deterministic": "deterministic",
    "jev": "Jev",
    "jev_to_llm": "Jev → LLM",
    "llm": "LLM",
    "none": "—",
}


def fmt_score(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def fmt_cost(value: float | None, complete: bool = True) -> str:
    if value is None:
        return "—"
    text = f"${value:.6f}" if value < 0.01 else f"${value:.4f}"
    return text if complete else f"{text}*"


def fmt_ms(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f} ms" if value < 10_000 else f"{value / 1000:.1f} s"


def route_text(route: str, escalation_reason: str | None = None) -> Text:
    label = ROUTE_LABEL.get(route, route)
    if escalation_reason == "requires_reasoning":
        label += " (reasoning)"
    elif escalation_reason == "primary_error" and route == "jev_to_llm":
        label += " (Jev error)"
    return Text(label, style=ROUTE_STYLE.get(route, ""))


def pass_text(passed: bool | None) -> Text:
    if passed is None:
        return Text("—", style="dim")
    return Text("pass", style="green") if passed else Text("fail", style="red bold")


def demo_badge(is_demo: bool) -> Text:
    return Text(" DEMO ", style="black on yellow") if is_demo else Text("")


def result_table(result: EvaluationResult, title: str | None = None) -> Table:
    table = Table(title=title, title_justify="left", expand=False, header_style="bold")
    table.add_column("Metric")
    table.add_column("Score", justify="right")
    table.add_column("Result")
    table.add_column("Route")
    table.add_column("Confidence", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Notes", overflow="fold", max_width=60)
    for m in result.metrics:
        if m.status == "skipped":
            table.add_row(
                m.display_name,
                "—",
                Text("skipped", style="dim"),
                route_text("none"),
                "—",
                "—",
                "—",
                Text(m.message or "", style="dim"),
            )
            continue
        if m.status == "error":
            table.add_row(
                m.display_name,
                "—",
                Text("error", style="red"),
                route_text(m.route),
                "—",
                fmt_ms(m.latency_ms),
                fmt_cost(m.cost_usd),
                Text(m.message or "", style="red"),
            )
            continue
        conf = fmt_score(m.confidence, 2)
        if m.escalated and m.judgments:
            conf = f"{fmt_score(m.judgments[0].confidence, 2)} → {conf}"
        note = m.explanation or ""
        if m.message:
            note = f"{m.message} {note}".strip()
        table.add_row(
            m.display_name,
            fmt_score(m.score),
            pass_text(m.passed),
            route_text(m.route, m.escalation_reason),
            conf,
            fmt_ms(m.latency_ms),
            fmt_cost(m.cost_usd, m.cost_complete),
            note[:240],
        )
    return table


def result_panel(result: EvaluationResult) -> Panel:
    header = Text.assemble(
        ("overall ", "bold"),
        (fmt_score(result.overall_score), "bold cyan"),
        "   ",
        pass_text(result.passed),
        f"   {fmt_ms(result.latency_ms)}   {fmt_cost(result.cost_usd)}"
        f"   escalations: {result.escalations}",
    )
    return Panel(Group(header, result_table(result)), title="EvalCascade", border_style="cyan")


def experiment_summary(experiment: Experiment) -> Group:
    s = experiment.summary
    r = s.routing
    kpis = Table.grid(padding=(0, 3))
    for _ in range(4):
        kpis.add_column()
    kpis.add_row(
        Text.assemble(("Overall ", "dim"), (fmt_score(s.overall_score), "bold cyan")),
        Text.assemble(("Pass rate ", "dim"), (fmt_pct(s.pass_rate), "bold")),
        Text.assemble(
            ("Cases ", "dim"),
            (str(s.num_cases), "bold"),
            ("  Evaluations ", "dim"),
            (str(s.num_evaluations), "bold"),
        ),
        Text.assemble(("Cost ", "dim"), (fmt_cost(s.cost_usd, s.cost_complete), "bold")),
    )
    kpis.add_row(
        Text.assemble(("Jev acceptance ", "dim"), (fmt_pct(r.jev_acceptance_rate), "bold green")),
        Text.assemble(("Escalation ", "dim"), (fmt_pct(r.escalation_rate), "bold yellow")),
        Text.assemble(("Deterministic ", "dim"), (fmt_pct(r.deterministic_rate), "bold cyan")),
        Text.assemble(
            ("Latency p50/p95 ", "dim"),
            (f"{fmt_ms(s.latency_ms.p50)} / {fmt_ms(s.latency_ms.p95)}", "bold"),
        ),
    )
    table = Table(header_style="bold", expand=False)
    table.add_column("Metric")
    table.add_column("Mean", justify="right")
    table.add_column("Pass", justify="right")
    table.add_column("n", justify="right")
    table.add_column("Det", justify="right", style="cyan")
    table.add_column("Jev", justify="right", style="green")
    table.add_column("Jev→LLM", justify="right", style="yellow")
    table.add_column("LLM", justify="right", style="magenta")
    table.add_column("Skip/Err", justify="right", style="dim")
    table.add_column("Cost", justify="right")
    for m in s.metrics.values():
        table.add_row(
            m.display_name,
            fmt_score(m.mean),
            fmt_pct(m.pass_rate),
            str(m.count),
            str(m.routes.deterministic),
            str(m.routes.jev),
            str(m.routes.jev_to_llm),
            str(m.routes.llm),
            f"{m.skipped}/{m.errors}",
            fmt_cost(m.cost_usd),
        )
    title = Text.assemble(
        ("Experiment ", "bold"),
        (experiment.name, "bold cyan"),
        f"  {experiment.id}  ",
        demo_badge(experiment.is_demo),
    )
    notes = (
        [Text("* cost incomplete: some evaluator calls reported no cost", style="dim")]
        if not s.cost_complete
        else []
    )
    return Group(title, kpis, table, *notes)


def experiments_table(items: list[ExperimentListItem]) -> Table:
    table = Table(header_style="bold")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Dataset")
    table.add_column("Created (UTC)")
    table.add_column("Cases", justify="right")
    table.add_column("Overall", justify="right")
    table.add_column("Pass", justify="right")
    table.add_column("Jev acc.", justify="right")
    table.add_column("Escal.", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("")
    for e in items:
        s = e.summary
        table.add_row(
            e.id,
            e.name,
            e.dataset_name or "—",
            e.created_at.strftime("%Y-%m-%d %H:%M"),
            str(s.num_cases),
            fmt_score(s.overall_score),
            fmt_pct(s.pass_rate),
            fmt_pct(s.routing.jev_acceptance_rate),
            fmt_pct(s.routing.escalation_rate),
            fmt_cost(s.cost_usd, s.cost_complete),
            demo_badge(e.is_demo),
        )
    return table


def datasets_table(items: list[DatasetInfo]) -> Table:
    table = Table(header_style="bold")
    table.add_column("Name")
    table.add_column("Cases", justify="right")
    table.add_column("Fields")
    table.add_column("Hash", style="dim")
    table.add_column("Path", overflow="fold")
    for d in items:
        fields = ", ".join(f"{k}:{v}" for k, v in d.fields.items() if v)
        table.add_row(d.name, str(d.num_cases), fields, d.hash, d.path or "—")
    return table


def _delta_text(
    d: Delta,
    *,
    higher_is_better: bool = True,
    pct: bool = False,
    cost: bool = False,
    ms: bool = False,
) -> Text:
    if d.delta is None:
        return Text("—", style="dim")
    good = d.delta > 0 if higher_is_better else d.delta < 0
    style = "dim" if abs(d.delta) < 1e-12 else ("green" if good else "red")
    if pct:
        value = f"{d.delta * 100:+.1f} pp"
    elif cost:
        value = f"{d.delta:+.6f}"
    elif ms:
        value = f"{d.delta:+.0f} ms"
    else:
        value = f"{d.delta:+.3f}"
    return Text(value, style=style)


def comparison_table(cmp: Comparison) -> Group:
    table = Table(header_style="bold")
    table.add_column("")
    table.add_column("Baseline", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Δ", justify="right")
    rows = [
        ("Overall score", cmp.overall_score, {}, fmt_score),
        ("Pass rate", cmp.pass_rate, {"pct": True}, fmt_pct),
        ("Jev acceptance rate", cmp.jev_acceptance_rate, {"pct": True}, fmt_pct),
        (
            "LLM escalation rate",
            cmp.escalation_rate,
            {"pct": True, "higher_is_better": False},
            fmt_pct,
        ),
        ("Total cost", cmp.cost_usd, {"cost": True, "higher_is_better": False}, fmt_cost),
        ("Cost / case", cmp.cost_per_case_usd, {"cost": True, "higher_is_better": False}, fmt_cost),
        ("Latency p50", cmp.latency_p50_ms, {"ms": True, "higher_is_better": False}, fmt_ms),
        ("Latency p95", cmp.latency_p95_ms, {"ms": True, "higher_is_better": False}, fmt_ms),
    ]
    for label, delta, opts, fmt in rows:
        table.add_row(label, fmt(delta.baseline), fmt(delta.candidate), _delta_text(delta, **opts))
    table.add_section()
    for name, delta in cmp.metrics.items():
        table.add_row(
            name, fmt_score(delta.baseline), fmt_score(delta.candidate), _delta_text(delta)
        )
    c = cmp.cases
    footer = Text(
        f"Cases: {c.matched} matched · {c.improved} improved · {c.regressed} regressed · "
        f"{c.unchanged} unchanged · {c.only_in_baseline} only in baseline · "
        f"{c.only_in_candidate} only in candidate",
        style="dim",
    )
    title = Text.assemble(
        ("Baseline ", "dim"),
        (cmp.baseline.name, "bold"),
        f" ({cmp.baseline.id}) ",
        demo_badge(cmp.baseline.is_demo),
        ("  vs  candidate ", "dim"),
        (cmp.candidate.name, "bold"),
        f" ({cmp.candidate.id}) ",
        demo_badge(cmp.candidate.is_demo),
    )
    warn = (
        []
        if cmp.dataset_match
        else [Text("! baseline and candidate were run on different datasets", style="yellow")]
    )
    return Group(title, *warn, table, footer)


def gate_panel(result: GateResult) -> Panel:
    table = Table(header_style="bold", expand=False)
    table.add_column("Check")
    table.add_column("Result")
    table.add_column("Details")
    for c in result.checks:
        table.add_row(
            c.name,
            Text("ok", style="green") if c.passed else Text("FAIL", style="red bold"),
            c.message,
        )
    title = "Regression gate: PASSED" if result.passed else "Regression gate: FAILED"
    return Panel(table, title=title, border_style="green" if result.passed else "red")


def make_console() -> Console:
    # Rich falls back to 80 columns without a TTY; CI logs are far more readable wider.
    width = None if sys.stdout.isatty() or os.environ.get("COLUMNS") else 160
    return Console(highlight=False, soft_wrap=False, width=width)
