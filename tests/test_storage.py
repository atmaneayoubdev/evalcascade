"""SQLite persistence: experiments, references, case rows and the dataset registry."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from evalcascade import EvalSuite
from evalcascade.config import Settings
from evalcascade.datasets import Dataset, load_sample
from evalcascade.demo import DEMO_RUNS, seed_demo
from evalcascade.errors import DatasetError, NotFoundError
from evalcascade.experiments import Experiment
from evalcascade.metrics import build_metrics
from evalcascade.storage.store import ExperimentStore, resolve_dataset
from tests.conftest import ScriptedEvaluator


def experiment(
    settings: Settings, name: str, confidence: float = 0.95, *, demo: bool = False
) -> Experiment:
    suite = EvalSuite(
        build_metrics(["answer_relevance", "citation_presence"]),
        evaluators={
            "jev": ScriptedEvaluator("jev", confidence=confidence),
            "llm": ScriptedEvaluator("llm", route_label="llm", level=1),
        },
        settings=settings,
    )
    return suite.run_sync(load_sample("rag_qa"), name=name, is_demo=demo)


def test_save_get_and_references(store: ExperimentStore, settings: Settings) -> None:
    a = experiment(settings, "baseline")
    b = experiment(settings, "baseline", confidence=0.5)
    b.created_at = a.created_at + timedelta(seconds=5)
    c = experiment(settings, "candidate")
    c.created_at = a.created_at + timedelta(seconds=10)
    for e in (a, b, c):
        store.save_experiment(e)
    assert store.resolve("baseline") == b.id  # latest with that name
    assert store.resolve("latest") == c.id and store.resolve("latest~2") == a.id
    assert store.resolve(a.id) == a.id and store.resolve(a.id[:6]) == a.id
    with pytest.raises(NotFoundError, match="not found"):
        store.resolve("does-not-exist")
    with pytest.raises(NotFoundError):
        store.resolve("latest~99")
    with pytest.raises(ValueError, match="already exists"):
        store.save_experiment(a)

    back = store.get_experiment(a.id)
    assert back.summary == a.summary and len(back.results) == len(a.results)
    assert back.created_at.tzinfo is not None
    assert back.results[0].case.id == a.results[0].case.id
    assert store.get_experiment(a.id, with_results=False).results == []
    assert store.count_experiments() == 3


def test_ambiguous_prefix(store: ExperimentStore, settings: Settings) -> None:
    a, b = experiment(settings, "x"), experiment(settings, "y")
    a.id, b.id = "abc111111111", "abc222222222"
    store.save_experiment(a)
    store.save_experiment(b)
    with pytest.raises(NotFoundError, match="ambiguous"):
        store.resolve("abc")


def test_list_filters_case_rows_and_delete(store: ExperimentStore, settings: Settings) -> None:
    real = experiment(settings, "real", confidence=0.5)
    demo = experiment(settings, "demo", demo=True)
    store.save_experiment(real)
    store.save_experiment(demo)
    assert {e.name for e in store.list_experiments()} == {"real", "demo"}
    assert [e.name for e in store.list_experiments(include_demo=False)] == ["real"]
    assert [e.name for e in store.list_experiments(name="demo")] == ["demo"]
    assert store.count_experiments(include_demo=False) == 1

    total, rows = store.case_rows(real.id, limit=5)
    assert total == 12 and len(rows) == 5 and rows[0].case_id == "rag-001"
    assert rows[0].metrics["answer_relevance"].route == "jev_to_llm"
    esc_total, _ = store.case_rows(real.id, filter="escalated")
    assert esc_total == 12
    passed, _ = store.case_rows(real.id, filter="passed")
    failed, _ = store.case_rows(real.id, filter="failed")
    assert passed + failed == 12
    _, page2 = store.case_rows(real.id, limit=5, offset=10)
    assert len(page2) == 2
    case = store.get_case(real.id, "rag-003")
    assert case.case.id == "rag-003" and case.metrics
    with pytest.raises(NotFoundError):
        store.get_case(real.id, "nope")

    assert store.delete_demo_experiments() == 1
    assert store.delete_experiment("real") == real.id
    assert store.count_experiments() == 0


def test_dataset_registry(store: ExperimentStore, tmp_path: Path) -> None:
    ds = load_sample("rag_qa")
    info = store.register_dataset(ds, name="rag", description="sample")
    assert info.num_cases == 12 and info.fields["context"] == 12 and info.description == "sample"
    assert (
        info.path is not None
        and Path(info.path).parent == (tmp_path / ".evalcascade" / "datasets").resolve()
    )
    assert Path(info.path).read_text(encoding="utf-8") == Path(str(ds.path)).read_text(
        encoding="utf-8"
    )
    with pytest.raises(DatasetError, match="already"):
        store.register_dataset(ds, name="rag")
    store.register_dataset(ds, name="rag", overwrite=True)
    assert [d.name for d in store.list_datasets()] == ["rag"]
    assert len(store.load_dataset("rag")) == 12
    mem = Dataset.from_records([{"input": "q"}], name="mem")
    assert store.register_dataset(mem).num_cases == 1  # written to the workspace
    store.delete_dataset("mem")
    with pytest.raises(NotFoundError):
        store.get_dataset_info("mem")
    with pytest.raises(NotFoundError):
        store.delete_dataset("mem")


def test_resolve_dataset_refs(store: ExperimentStore, tmp_path: Path) -> None:
    assert resolve_dataset("sample:agent_tasks").name == "agent_tasks"
    path = load_sample("support_bot").to_jsonl(tmp_path / "s.jsonl")
    assert len(resolve_dataset(path)) == 10
    store.register_dataset(load_sample("rag_qa"), name="registered")
    assert len(resolve_dataset("registered", store)) == 12
    with pytest.raises(DatasetError, match="not found"):
        resolve_dataset("nothing", store)


def test_seed_demo(store: ExperimentStore) -> None:
    created = seed_demo(store)
    assert len(created) == len(DEMO_RUNS)
    items = store.list_experiments()
    assert all(e.is_demo for e in items) and len(items) == len(DEMO_RUNS)
    assert all(
        j.evaluator_kind in {"simulated", "deterministic"}
        for r in created[0].results
        for m in r.metrics
        for j in m.judgments
    )
    seed_demo(store)  # replaces, does not duplicate
    assert store.count_experiments() == len(DEMO_RUNS)
    assert store.ping()


def test_store_never_persists_secrets(tmp_path: Path) -> None:
    from tests.conftest import FAKE_KEY

    settings = Settings.load(
        env={"OPENROUTER_API_KEY": FAKE_KEY}, load_dotenv=False, home=tmp_path / "h"
    )
    db = tmp_path / "secret.db"
    store = ExperimentStore(f"sqlite:///{db.as_posix()}")
    suite = EvalSuite(
        build_metrics(["answer_relevance"]),
        evaluators={"jev": ScriptedEvaluator("jev")},
        settings=settings,
    )
    exp = suite.run_sync(load_sample("support_bot"), name="s")
    store.save_experiment(exp)
    store.dispose()
    assert FAKE_KEY.encode() not in db.read_bytes()
    assert FAKE_KEY not in exp.to_json()
