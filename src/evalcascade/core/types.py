"""Input data model: what is being evaluated.

An :class:`EvaluationRequest` is a single interaction of the system under test — a prompt,
the system's output, optional retrieved context, optional expected values, and (for agents)
an :class:`AgentTrace` of the steps and tool calls that produced the output.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolSpec(BaseModel):
    """A tool that was available to an agent."""

    name: str
    description: str = ""
    parameters: dict[str, Any] | None = Field(
        default=None, description="JSON Schema for the tool arguments."
    )


class ToolCall(BaseModel):
    """A single tool invocation made by an agent."""

    id: str | None = None
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: str | None = None

    @field_validator("arguments", mode="before")
    @classmethod
    def _parse_arguments(cls, value: Any) -> Any:
        # OpenAI-style traces carry arguments as a JSON string.
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {"_raw": value}
            return parsed if isinstance(parsed, dict) else {"_value": parsed}
        return {} if value is None else value

    def signature(self) -> str:
        """Stable identity of the call (tool name + canonical arguments)."""
        return f"{self.name}:{json.dumps(self.arguments, sort_keys=True, default=str)}"


class TraceStep(BaseModel):
    """One step of an agent trajectory."""

    type: Literal["thought", "tool_call", "message"] = "tool_call"
    content: str | None = None
    tool_call: ToolCall | None = None
    latency_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTrace(BaseModel):
    """The trajectory an agent took to produce its final output."""

    steps: list[TraceStep] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list, description="Tools available to the agent.")

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [s.tool_call for s in self.steps if s.tool_call is not None]

    def tool_call_steps(self) -> list[tuple[int, ToolCall]]:
        """``(step_index, tool_call)`` pairs in trajectory order."""
        return [(i, s.tool_call) for i, s in enumerate(self.steps) if s.tool_call is not None]

    def tool_spec(self, name: str) -> ToolSpec | None:
        return next((t for t in self.tools if t.name == name), None)


class Expected(BaseModel):
    """Optional ground truth. Unknown keys are preserved for custom metrics.

    Known keys:
      * ``answer`` — reference answer (string) or list of acceptable answers
      * ``tools`` — tool names the agent is expected to call
      * ``tool_calls`` — expected calls with arguments
      * ``max_tool_calls`` — upper bound on an efficient trajectory
      * ``label`` — a gold label, used by the benchmark harness
    """

    model_config = ConfigDict(extra="allow")

    answer: str | list[str] | None = None
    tools: list[str] | None = None
    tool_calls: list[ToolCall] | None = None
    max_tool_calls: int | None = None
    label: Any = None

    def answers(self) -> list[str]:
        if self.answer is None:
            return []
        return [self.answer] if isinstance(self.answer, str) else list(self.answer)


class EvaluationRequest(BaseModel):
    """A single interaction to evaluate."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    input: str | None = None
    output: str | None = None
    context: list[str] = Field(default_factory=list)
    expected: Expected | None = None
    trace: AgentTrace | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("context", mode="before")
    @classmethod
    def _coerce_context(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("expected", mode="before")
    @classmethod
    def _coerce_expected(cls, value: Any) -> Any:
        # Allow a bare string as shorthand for {"answer": ...}.
        if isinstance(value, str):
            return {"answer": value}
        return value

    def has(self, field: str) -> bool:
        """Whether a request field is present and non-empty."""
        value = getattr(self, field, None)
        if value is None:
            return False
        if isinstance(value, str | list | dict):
            return len(value) > 0
        if isinstance(value, AgentTrace):
            return len(value.steps) > 0
        return True


class Usage(BaseModel):
    """Token usage of a provider call."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )
