"""Run a suite over a dataset, record experiments, compare them and apply a regression gate.

Uses the bundled synthetic ``rag_qa`` sample. Requires OPENROUTER_API_KEY (and a judge).
Experiments are stored in ./.evalcascade/evalcascade.db — view them with ``evalcascade serve``.

    uv run python examples/dataset_eval.py
"""

import asyncio

from evalcascade import EvalSuite, EvaluationPolicy, RegressionGate, compare_experiments
from evalcascade.datasets import load_sample
from evalcascade.metrics import build_metrics
from evalcascade.storage import ExperimentStore


async def main() -> None:
    dataset = load_sample("rag_qa")  # or Dataset.from_jsonl("my_cases.jsonl")
    store = ExperimentStore.from_settings()

    async with EvalSuite(build_metrics(["rag"]), policy=EvaluationPolicy.cascade(0.82)) as suite:
        baseline = await suite.run(dataset, name="rag-baseline", store=store)
    async with EvalSuite(build_metrics(["rag"]), policy=EvaluationPolicy.cascade(0.6)) as suite:
        candidate = await suite.run(dataset, name="rag-threshold-0.6", store=store)

    for exp in (baseline, candidate):
        s = exp.summary
        print(
            f"{exp.name:<18} overall={s.overall_score:.3f} pass={s.pass_rate:.0%} "
            f"jev_acceptance={s.routing.jev_acceptance_rate or 0:.0%} "
            f"escalation={s.routing.escalation_rate or 0:.0%} cost=${s.cost_usd:.5f} "
            f"p50={s.latency_ms.p50:.0f}ms"
        )

    comparison = compare_experiments(baseline, candidate)
    overall, cost = comparison.overall_score.delta, comparison.cost_usd.delta
    print(f"\noverall delta: {overall:+.3f}  cost delta: ${cost:+.5f}")

    gate = RegressionGate(max_quality_drop=0.03, metric_thresholds={"groundedness": 0.05})
    result = gate.evaluate(baseline, candidate)
    print(result.to_text())

    baseline.to_json("baseline.json")  # commit this and gate CI runs against it
    store.dispose()


if __name__ == "__main__":
    asyncio.run(main())
