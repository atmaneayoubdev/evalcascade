"""Regenerate the offline regression-gate fixtures in examples/ci/ (no API keys needed).

* ``baseline.json``  — deterministic metrics over the bundled ``rag_qa`` sample
* ``candidate.json`` — the same system re-run (the gate should pass)
* ``regressed.json`` — citations stripped from half of the answers (the gate should fail)

    uv run python scripts/make_ci_fixtures.py
"""

from __future__ import annotations

import re
from pathlib import Path

from evalcascade import EvalSuite, EvaluationPolicy
from evalcascade.config import Settings
from evalcascade.datasets import Dataset, load_sample
from evalcascade.metrics import CitationCorrectness, CitationPresence, Safety

OUT = Path(__file__).resolve().parents[1] / "examples" / "ci"
CITATION = re.compile(r"\s*\[\d+\]")


def run(dataset: Dataset, name: str, notes: str) -> None:
    suite = EvalSuite(
        [CitationPresence(), CitationCorrectness(), Safety()],
        policy=EvaluationPolicy.deterministic_only(),
        settings=Settings.load(env={}, load_dotenv=False),
    )
    experiment = suite.run_sync(dataset, name=name, notes=notes, tags=["ci-fixture"])
    experiment.to_json(OUT / f"{name}.json")
    print(f"{name}: overall={experiment.summary.overall_score:.3f} -> {OUT / (name + '.json')}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rag = load_sample("rag_qa")
    run(rag, "baseline", "Offline CI fixture: deterministic metrics on the rag_qa sample.")
    run(rag, "candidate", "Offline CI fixture: unchanged system (gate passes).")
    stripped = [
        c.model_copy(update={"output": CITATION.sub("", c.output or "")}) if i % 2 == 0 else c
        for i, c in enumerate(rag.cases)
    ]
    regressed = rag.model_copy(update={"cases": stripped})
    run(regressed, "regressed", "Offline CI fixture: half the answers lose citations (gate fails).")


if __name__ == "__main__":
    main()
