"""FastAPI smoke tests against a seeded store (no network)."""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

from evalcascade.api.app import create_app
from evalcascade.config import Settings
from evalcascade.datasets import load_sample
from evalcascade.demo import seed_demo
from evalcascade.storage.store import ExperimentStore

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings.load(env={}, load_dotenv=False, home=tmp_path / "ws")
    store = ExperimentStore.from_settings(settings)
    seed_demo(store)
    store.register_dataset(load_sample("rag_qa"))
    with TestClient(create_app(settings, store)) as c:
        yield c


def test_health_config_metrics(client: TestClient) -> None:
    assert client.get("/api/health").json() == {
        "status": "ok",
        "version": "0.1.0",
        "database": "ok",
    }
    cfg = client.get("/api/config").json()
    assert (
        cfg["openrouter_api_key_configured"] is False and cfg["jev"]["model"] == "typesafe/jev-1.13"
    )
    assert cfg["policy"]["escalate_below"] == 0.82
    metrics = client.get("/api/metrics").json()
    assert len(metrics) == 13 and {"name", "primitives", "deterministic", "required_fields"} <= set(
        metrics[0]
    )
    assert "rag" in client.get("/api/metrics/suites").json()


def test_overview(client: TestClient) -> None:
    ov = client.get("/api/overview").json()
    assert ov["has_demo_data"] is True and ov["has_real_data"] is False
    assert ov["totals"]["experiments"] == 6 and len(ov["recent"]) == 6 and len(ov["trend"]) == 6
    assert ov["trend"][0]["created_at"] < ov["trend"][-1]["created_at"]
    names = {r["name"]: r for r in ov["regressions"]}
    assert (
        names["rag-assistant"]["regressed"] is True and names["agent-planner"]["regressed"] is False
    )
    assert sum(ov["routing"].values()) > 0
    empty = client.get("/api/overview?include_demo=false").json()
    assert empty["totals"]["experiments"] == 0 and empty["averages"]["overall_score"] is None


def test_experiments_cases_compare_gate(client: TestClient) -> None:
    items = client.get("/api/experiments?limit=10").json()
    assert len(items) == 6 and all(i["is_demo"] for i in items)
    assert client.get("/api/experiments?include_demo=false").json() == []
    exp_id = items[0]["id"]
    detail = client.get(f"/api/experiments/{exp_id}").json()
    assert detail["id"] == exp_id and "results" not in detail and detail["dataset"]["size"] > 0
    assert detail["evaluators"]["jev"]["kind"] == "simulated"
    page = client.get(f"/api/experiments/{exp_id}/cases?limit=3").json()
    assert page["total"] >= 3 and len(page["items"]) == 3 and page["limit"] == 3
    row = page["items"][0]
    assert {"case_id", "input_preview", "metrics", "has_trace"} <= set(row)
    case = client.get(f"/api/experiments/{exp_id}/cases/{row['case_id']}").json()
    assert case["case"]["id"] == row["case_id"] and case["metrics"][0]["judgments"]
    escalated = client.get(f"/api/experiments/{exp_id}/cases?filter=escalated").json()
    assert all(r["escalations"] > 0 for r in escalated["items"])
    assert client.get(f"/api/experiments/{exp_id}/cases?filter=bogus").status_code == 422

    cmp = client.get("/api/compare", params={"baseline": "latest~2", "candidate": "latest"}).json()
    assert cmp["dataset_match"] is True and "groundedness" in cmp["metrics"]
    gate = client.post(
        "/api/gate", json={"baseline": "latest~2", "candidate": "latest", "max_quality_drop": 0.0}
    ).json()
    assert gate["passed"] is False and gate["violations"]
    assert client.get("/api/experiments/missing").status_code == 404
    assert (
        client.get("/api/compare", params={"baseline": "x", "candidate": "latest"}).status_code
        == 404
    )
    assert client.delete(f"/api/experiments/{exp_id}").json() == {"deleted": exp_id}


def test_datasets(client: TestClient) -> None:
    listed = client.get("/api/datasets").json()
    assert [d["name"] for d in listed] == ["rag_qa"] and listed[0]["fields"]["context"] == 12
    detail = client.get("/api/datasets/rag_qa?limit=2&offset=1").json()
    assert detail["cases"]["total"] == 12 and [c["id"] for c in detail["cases"]["items"]] == [
        "rag-002",
        "rag-003",
    ]
    created = client.post(
        "/api/datasets", json={"name": "uploaded", "cases": [{"input": "q", "output": "a"}]}
    )
    assert created.status_code == 201 and created.json()["num_cases"] == 1
    assert (
        client.post(
            "/api/datasets", json={"name": "uploaded", "cases": [{"input": "q"}]}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/datasets", json={"name": "../evil", "cases": [{"input": "q"}]}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/datasets", json={"name": "bad", "cases": [{"context": 5}]}).status_code
        == 400
    )
    assert client.get("/api/datasets/nope").status_code == 404


def test_evaluate(client: TestClient) -> None:
    ok = client.post(
        "/api/evaluate",
        json={
            "output": "Answer [1]",
            "context": ["x"],
            "metrics": ["citation_presence", {"name": "safety"}],
            "policy": "deterministic",
        },
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["metrics"][0]["score"] == 1.0 and body["metrics"][1]["status"] == "skipped"
    missing_key = client.post(
        "/api/evaluate", json={"input": "q", "output": "a", "metrics": ["answer_relevance"]}
    )
    assert missing_key.status_code == 400 and "OPENROUTER_API_KEY" in missing_key.json()["detail"]
    assert (
        client.post(
            "/api/evaluate", json={"metrics": ["nope"], "policy": "deterministic"}
        ).status_code
        == 400
    )
    assert (
        client.post("/api/evaluate", json={"metrics": [], "policy": "deterministic"}).status_code
        == 400
    )


def test_openapi_and_root(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    for path in (
        "/api/health",
        "/api/evaluate",
        "/api/experiments",
        "/api/compare",
        "/api/gate",
        "/api/overview",
        "/api/metrics",
        "/api/datasets",
    ):
        assert path in spec["paths"]
    root = client.get("/")
    assert root.status_code == 200


def test_bearer_token_auth(tmp_path: Path) -> None:
    settings = Settings.load(
        env={"EVALCASCADE_API_TOKEN": "s3cret-token-value"}, load_dotenv=False, home=tmp_path / "ws"
    )
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/health").status_code == 200  # health stays public
        assert c.get("/api/experiments").status_code == 401
        assert (
            c.get("/api/experiments", headers={"Authorization": "Bearer wrong"}).status_code == 401
        )
        assert (
            c.get(
                "/api/experiments", headers={"Authorization": "Bearer s3cret-token-value"}
            ).status_code
            == 200
        )
        assert (
            "s3cret"
            not in c.get("/api/config", headers={"Authorization": "Bearer s3cret-token-value"}).text
        )


def test_serves_dashboard_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = tmp_path / "dash"
    (bundle / "experiments").mkdir(parents=True)
    (bundle / "index.html").write_text("<html>overview</html>", encoding="utf-8")
    (bundle / "experiments" / "index.html").write_text("<html>experiments</html>", encoding="utf-8")
    monkeypatch.setenv("EVALCASCADE_DASHBOARD_DIR", str(bundle))
    settings = Settings.load(env={}, load_dotenv=False, home=tmp_path / "ws")
    with TestClient(create_app(settings)) as c:
        assert "overview" in c.get("/").text
        assert "experiments" in c.get("/experiments/").text
        assert c.get("/api/health").status_code == 200
