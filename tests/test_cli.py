"""CLI smoke tests (no network: demo data and deterministic policies only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evalcascade import __version__
from evalcascade.cli.app import app

runner = CliRunner()


def invoke(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args), catch_exceptions=False)
    return result.exit_code, result.output


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    code, out = invoke("init", str(tmp_path), "--demo")
    assert code == 0, out
    return tmp_path


def test_version_and_help() -> None:
    assert invoke("--version") == (0, f"evalcascade {__version__}\n")
    code, out = invoke("--help")
    assert code == 0
    for command in (
        "init",
        "evaluate",
        "run",
        "datasets",
        "experiments",
        "compare",
        "gate",
        "serve",
        "doctor",
        "metrics",
        "demo",
    ):
        assert command in out


def test_init_creates_workspace(workspace: Path) -> None:
    assert (workspace / "evalcascade.toml").is_file()
    assert (workspace / "datasets" / "rag_qa.jsonl").is_file()
    assert ".env" in (workspace / ".gitignore").read_text(encoding="utf-8")
    code, out = invoke("init", str(workspace))
    assert code == 0 and "keeping existing" in out


def test_experiments_compare_gate_roundtrip(workspace: Path) -> None:
    code, out = invoke("experiments", "list")
    assert code == 0 and "rag-assistant" in out and "DEMO" in out
    code, out = invoke("experiments", "show", "rag-assistant", "--cases")
    assert code == 0 and "Jev acceptance" in out and "rag-001" in out
    code, out = invoke("experiments", "show", "rag-assistant", "--case", "rag-001")
    assert code == 0 and "Groundedness" in out

    export = workspace / "baseline.json"
    assert invoke("experiments", "export", "latest~1", "-o", str(export))[0] == 0
    assert json.loads(export.read_text(encoding="utf-8"))["results"]

    code, out = invoke("compare", str(export), "latest")
    assert code == 0 and "Overall score" in out
    code, out = invoke("compare", "latest~1", "latest", "--json")
    assert code == 0 and json.loads(out)["overall_score"]["baseline"] is not None

    # the demo's newest rag-assistant run is a regression of the previous one
    ids = [
        line.split()[1]
        for line in invoke("experiments", "list", "--name", "rag-assistant")[1].splitlines()
        if "rag-assistant" in line
    ]
    assert len(ids) == 3
    summary = workspace / "summary.md"
    code, out = invoke(
        "gate",
        "--baseline",
        ids[1],
        "--candidate",
        ids[0],
        "--max-quality-drop",
        "0.01",
        "--summary-file",
        str(summary),
    )
    assert code == 1 and "FAILED" in out
    assert "regression gate failed" in summary.read_text(encoding="utf-8")
    code, out = invoke("gate", "-b", ids[1], "-c", ids[1], "--format", "json")
    assert code == 0 and json.loads(out)["passed"] is True
    code, out = invoke(
        "gate", "-b", ids[1], "-c", ids[0], "--max-quality-drop", "1", "--format", "markdown"
    )
    assert code == 0 and "| Check |" in out


def test_gate_argument_errors(workspace: Path) -> None:
    code, _ = invoke("gate", "-b", "latest", "--metric-threshold", "groundedness")
    assert code == 2
    code, _ = invoke("gate", "-b", "no-such-experiment")
    assert code == 2


def test_run_and_evaluate_deterministic(workspace: Path) -> None:
    out_json = workspace / "run.json"
    code, out = invoke(
        "run",
        "datasets/rag_qa.jsonl",
        "-m",
        "citation_presence",
        "-p",
        "deterministic",
        "--name",
        "det",
        "-o",
        str(out_json),
        "--limit",
        "5",
    )
    assert code == 0, out
    assert "Citation Presence" in out and "saved experiment" in out
    assert json.loads(out_json.read_text(encoding="utf-8"))["summary"]["num_cases"] == 5
    code, out = invoke(
        "run", "sample:support_bot", "-m", "safety", "-p", "deterministic", "--no-save"
    )
    assert code == 0 and "saved experiment" not in out

    code, out = invoke(
        "evaluate", "-o", "card 4111 1111 1111 1111", "-m", "safety", "-p", "deterministic"
    )
    assert code == 0 and "payment_card" in out
    code, out = invoke("evaluate", "-o", "see [1]", "-m", "citation_presence", "--json")
    assert code == 0 and json.loads(out)["metrics"][0]["score"] == 1.0


def test_run_without_key_fails_fast(workspace: Path) -> None:
    code, out = invoke("run", "datasets/support_bot.jsonl", "-s", "general", "--no-save")
    assert code == 2
    assert "OPENROUTER_API_KEY" in out


def test_run_unknown_dataset(workspace: Path) -> None:
    assert invoke("run", "nope.jsonl")[0] == 2


def test_datasets_commands(workspace: Path) -> None:
    code, out = invoke("datasets", "list")
    assert code == 0 and "rag_qa" in out
    code, out = invoke("datasets", "show", "rag_qa", "-n", "1")
    assert code == 0 and "rag-001" in out and "12 cases" in out
    code, out = invoke("datasets", "create", "mine", "--template", "agent")
    assert code == 0 and (workspace / "datasets" / "mine.jsonl").is_file()
    assert invoke("datasets", "create", "mine")[0] == 2
    assert invoke("datasets", "create", "other", "--template", "nope")[0] == 2
    code, out = invoke("datasets", "validate", "datasets/mine.jsonl")
    assert code == 0 and "valid" in out
    bad = workspace / "bad.jsonl"
    bad.write_text("{oops}\n", encoding="utf-8")
    assert invoke("datasets", "validate", str(bad))[0] == 1
    code, out = invoke("datasets", "import", "datasets/mine.jsonl", "--name", "imported")
    assert code == 0 and "imported" in out
    assert invoke("datasets", "import", "datasets/mine.jsonl", "--name", "imported")[0] == 2


def test_experiments_import_delete_and_demo_clear(workspace: Path) -> None:
    export = workspace / "e.json"
    invoke("experiments", "export", "latest", "-o", str(export))
    assert invoke("experiments", "import", str(export))[0] == 2  # already exists
    code, out = invoke("experiments", "delete", "latest", "--yes")
    assert code == 0 and "deleted" in out
    assert invoke("experiments", "import", str(export))[0] == 0
    code, out = invoke("demo", "--clear")
    assert code == 0 and "removed" in out
    code, out = invoke("experiments", "list")
    assert "No experiments yet" in out
    code, out = invoke("demo")
    assert code == 0 and "DEMO" in out


def test_metrics_and_doctor(workspace: Path) -> None:
    code, out = invoke("metrics")
    assert code == 0 and "groundedness" in out and "suites:" in out
    code, out = invoke("doctor")
    assert code == 0
    assert "OPENROUTER_API_KEY" in out and "not set" in out and "Database" in out
