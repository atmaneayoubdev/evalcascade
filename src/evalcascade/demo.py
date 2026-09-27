"""Seed **demonstration** experiments (simulated judgments, no API calls, ``is_demo=True``).

Used by ``evalcascade demo`` so the dashboard has something to show on first run. Demo
experiments are always labelled as such in the CLI, the API and the dashboard, and can be
removed with ``evalcascade demo --clear``.
"""

from __future__ import annotations

from datetime import timedelta

from evalcascade.config import Settings
from evalcascade.core.policy import EvaluationPolicy
from evalcascade.core.suite import EvaluationSuite
from evalcascade.datasets import load_sample
from evalcascade.evaluators.simulated import SimulatedEvaluator
from evalcascade.experiments.experiment import Experiment, utcnow
from evalcascade.metrics import build_metrics
from evalcascade.storage.store import ExperimentStore

# (experiment name, sample dataset, metric suite, simulated quality, seed, days ago)
DEMO_RUNS: tuple[tuple[str, str, list[str], float, str, float], ...] = (
    ("support-bot", "support_bot", ["general"], 0.80, "support-v1", 6.0),
    ("rag-assistant", "rag_qa", ["rag", "citation_correctness"], 0.84, "rag-v1", 5.0),
    ("agent-planner", "agent_tasks", ["agent"], 0.78, "agent-v1", 4.0),
    ("rag-assistant", "rag_qa", ["rag", "citation_correctness"], 0.88, "rag-v2", 2.5),
    ("agent-planner", "agent_tasks", ["agent"], 0.84, "agent-v2", 1.5),
    ("rag-assistant", "rag_qa", ["rag", "citation_correctness"], 0.74, "rag-v3", 0.2),
)


def seed_demo(store: ExperimentStore, *, replace: bool = True) -> list[Experiment]:
    """Create the demo experiments in ``store``. Returns them oldest-first."""
    if replace:
        store.delete_demo_experiments()
    settings = Settings.load(env={}, load_dotenv=False)
    now = utcnow()
    created: list[Experiment] = []
    for name, sample, suite_names, quality, seed, days_ago in DEMO_RUNS:
        evaluators = {
            "jev": SimulatedEvaluator("jev", role="jev", seed=seed, quality=quality),
            "llm": SimulatedEvaluator(
                "llm", role="llm", seed=seed, quality=min(0.97, quality + 0.08)
            ),
        }
        suite = EvaluationSuite(
            build_metrics(suite_names),
            policy=EvaluationPolicy.cascade(),
            evaluators=evaluators,
            settings=settings,
        )
        experiment = suite.run_sync(
            load_sample(sample),
            name=name,
            is_demo=True,
            tags=["demo", seed],
            notes="Demonstration data produced by the simulated evaluator — not a real evaluation.",
        )
        experiment.created_at = now - timedelta(days=days_ago)
        store.save_experiment(experiment)
        created.append(experiment)
    return created
