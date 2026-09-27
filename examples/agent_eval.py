"""Evaluate an agent trajectory: tool choice, arguments, efficiency and task success.

Deterministic checks run when ground truth is given (``expected.tools``, ``max_tool_calls``);
the remaining judgments go through the cascade. Requires OPENROUTER_API_KEY.

    uv run python examples/agent_eval.py
"""

from evalcascade import AgentTrace, EvalSuite, ToolCall, ToolSpec, TraceStep
from evalcascade.metrics import (
    TaskSuccess,
    ToolArgumentsQuality,
    ToolSelection,
    TrajectoryEfficiency,
    UnnecessaryToolCalls,
)

weather = ToolSpec(
    name="get_weather",
    description="Current weather for a city.",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}, "unit": {"enum": ["celsius", "fahrenheit"]}},
        "required": ["city"],
    },
)
search = ToolSpec(name="web_search", description="Search the web.")

trace = AgentTrace(
    tools=[weather, search],
    steps=[
        TraceStep(type="thought", content="I'll search first."),
        TraceStep(tool_call=ToolCall(name="web_search", arguments={"query": "lisbon weather"})),
        TraceStep(
            tool_call=ToolCall(
                name="get_weather",
                arguments={"city": "Lisbon", "unit": "celsius"},
                result={"temp": 22},
            )
        ),
        TraceStep(
            tool_call=ToolCall(
                name="get_weather",
                arguments={"city": "Lisbon", "unit": "celsius"},
                result={"temp": 22},
            )
        ),
        TraceStep(type="message", content="It's 22 °C in Lisbon."),
    ],
)

suite = EvalSuite(
    metrics=[
        TaskSuccess(),
        ToolSelection(),
        ToolArgumentsQuality(),
        TrajectoryEfficiency(),
        UnnecessaryToolCalls(),
    ]
)
result = suite.evaluate_sync(
    input="What's the weather in Lisbon in celsius?",
    output="It's 22 °C in Lisbon.",
    trace=trace,
    expected={"tools": ["get_weather"], "max_tool_calls": 1},
)

print(result.summary())
print("\nper-step judgments:")
for m in result.metrics:
    for step in m.details.get("steps", []):
        print(f"  step {step['step_index']}: {m.metric:<24} {step['label']}")
