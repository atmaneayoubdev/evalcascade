"""The System One -> System Two cascade, up close.

Shows global and per-metric escalation thresholds, and inspects the judgment chain: what Jev
decided, how confident it was, whether it escalated, and what that cost. Then runs the same
case under the Jev-only and LLM-only presets for comparison.

Requires OPENROUTER_API_KEY and a judge (see examples/basic.py).

    uv run python examples/cascade.py
"""

import asyncio

from evalcascade import EvalSuite, EvaluationPolicy, MetricPolicy
from evalcascade.metrics import AnswerRelevance, Groundedness, Safety

CASE = {
    "input": "How long are backups kept on the Starter plan?",
    "output": "Starter plans keep backups for 7 days, and you can restore to any point in time.",
    "context": [
        "Backups are retained for 30 days on Business plans and 7 days on Starter. "
        "Point-in-time restore is available only on Business plans."
    ],
}

POLICIES = {
    "cascade": EvaluationPolicy(
        deterministic_first=True,
        primary="jev",
        fallback="llm",
        escalate_below=0.82,
        # stricter escalation for groundedness, never escalate safety
        overrides={
            "groundedness": MetricPolicy(escalate_below=0.9),
            "safety": MetricPolicy(escalate=False),
        },
    ),
    "jev only": EvaluationPolicy.jev_only(),
    "llm only": EvaluationPolicy.llm_only(),
}


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


async def main() -> None:
    metrics = [AnswerRelevance(), Groundedness(), Safety()]
    for label, policy in POLICIES.items():
        async with EvalSuite(metrics, policy=policy) as suite:
            result = await suite.evaluate(**CASE)
        print(
            f"\n== {label}: overall {result.overall_score:.3f}, cost ${result.cost_usd:.6f}, "
            f"{result.latency_ms:.0f} ms, {result.escalations} escalation(s)"
        )
        for m in result.metrics:
            chain = " -> ".join(
                f"{j.evaluator}(score={j.score:.2f}, conf={fmt(j.confidence)})" for j in m.judgments
            )
            reason = f" [{m.escalation_reason}]" if m.escalation_reason else ""
            print(f"  {m.metric:<17} {m.route:<11}{reason:<18} {chain}")


if __name__ == "__main__":
    asyncio.run(main())
