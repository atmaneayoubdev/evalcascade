"""Evaluate one answer with three metrics.

Requires OPENROUTER_API_KEY (Jev) — and a judge for escalations (OpenRouter by default, or set
EVALCASCADE_JUDGE_BASE_URL / _API_KEY / _MODEL for any OpenAI-compatible endpoint).

    uv run python examples/basic.py
"""

from evalcascade import EvalSuite
from evalcascade.metrics import AnswerRelevance, Correctness, Safety

suite = EvalSuite(metrics=[AnswerRelevance(), Correctness(), Safety()])

result = suite.evaluate_sync(
    input="What is the boiling point of water at sea level?",
    output="Water boils at 100 °C (212 °F) at sea level.",
    expected="100 °C",
)

print(f"overall score: {result.overall_score:.3f}  passed: {result.passed}")
for m in result.metrics:
    print(f"  {m.display_name:<18} {m.score:.3f}  via {m.route:<13} {m.explanation or ''}")
print(f"cost: ${result.cost_usd:.6f}  latency: {result.latency_ms:.0f} ms")
