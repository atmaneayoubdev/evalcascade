"""Agent / tool-use metrics.

Each metric is deterministic when ground truth is available (``expected.tools``,
``expected.tool_calls``, ``expected.max_tool_calls``, ``expected.answer``) and falls back to
bounded semantic questions — usually one yes/no question per tool call — otherwise.
Deterministic facts (duplicate calls, schema violations) are computed by code and passed to
the judge as finished labels. Per-step outcomes are reported in ``details["steps"]`` so the
dashboard can annotate the trace.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from evalcascade.core.metric import Aggregation, DeterministicOutcome, Metric
from evalcascade.core.rubric import Answer, BinaryQuestion, Rubric, ScoreQuestion
from evalcascade.core.types import AgentTrace, EvaluationRequest, ToolCall, ToolSpec
from evalcascade.metrics._text import compact, matches_reference, truncate

MAX_CALLS = 15


# ---------------------------------------------------------------------------
# Trace helpers
# ---------------------------------------------------------------------------


def _calls(request: EvaluationRequest) -> list[tuple[int, ToolCall]]:
    return request.trace.tool_call_steps() if request.trace else []


def tools_state(trace: AgentTrace, *, with_schema: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tool in trace.tools:
        if with_schema and tool.parameters:
            out[tool.name] = {"description": tool.description, "parameters": compact(tool.parameters, 1500)}
        else:
            out[tool.name] = tool.description
    return out


def call_state(call: ToolCall, *, result_chars: int = 600) -> dict[str, Any]:
    state: dict[str, Any] = {"tool": call.name, "arguments": compact(call.arguments, 1500)}
    if call.error:
        state["error"] = truncate(call.error, result_chars)
    elif call.result is not None:
        state["result"] = compact(call.result, result_chars)
    return state


def trajectory_state(trace: AgentTrace, *, max_steps: int = 40) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for i, step in enumerate(trace.steps[:max_steps]):
        item: dict[str, Any] = {"step": i + 1, "type": step.type}
        if step.content:
            item["content"] = truncate(step.content, 500)
        if step.tool_call:
            item.update(call_state(step.tool_call, result_chars=400))
        steps.append(item)
    if len(trace.steps) > max_steps:
        steps.append({"note": f"{len(trace.steps) - max_steps} more steps omitted"})
    return steps


def duplicate_indices(calls: list[tuple[int, ToolCall]]) -> set[int]:
    """Positions (into ``calls``) of calls identical to an earlier call."""
    seen: set[str] = set()
    dups: set[int] = set()
    for pos, (_, call) in enumerate(calls):
        sig = call.signature()
        if sig in seen:
            dups.add(pos)
        seen.add(sig)
    return dups


def validate_arguments(arguments: dict[str, Any], spec: ToolSpec | None) -> list[str]:
    """Minimal JSON-Schema check: required keys, primitive types, enums, extra keys."""
    if spec is None:
        return []
    schema = spec.parameters or {}
    if not schema:
        return []
    errors: list[str] = []
    props: dict[str, Any] = schema.get("properties", {}) or {}
    for key in schema.get("required", []) or []:
        if key not in arguments:
            errors.append(f"missing required argument '{key}'")
    if schema.get("additionalProperties") is False:
        errors.extend(f"unexpected argument '{k}'" for k in arguments if k not in props)
    type_map: dict[str, tuple[type, ...]] = {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "array": (list,),
        "object": (dict,),
    }
    for key, value in arguments.items():
        prop = props.get(key)
        if not isinstance(prop, dict):
            continue
        expected = prop.get("type")
        types = expected if isinstance(expected, list) else [expected] if expected else []
        if types and value is not None:
            allowed = tuple(t for name in types for t in type_map.get(name, ()))
            is_bool_mismatch = isinstance(value, bool) and "boolean" not in types
            if allowed and (not isinstance(value, allowed) or is_bool_mismatch):
                errors.append(f"argument '{key}' should be {'/'.join(types)}")
        if "enum" in prop and value not in prop["enum"]:
            errors.append(f"argument '{key}' must be one of {prop['enum']}")
    return errors


def _step(step_index: int, label: str, score: float | None, explanation: str | None = None) -> dict[str, Any]:
    return {"step_index": step_index, "label": label, "score": score, "explanation": explanation}


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    if isinstance(a, int | float) and isinstance(b, int | float) and not isinstance(a, bool):
        return abs(float(a) - float(b)) < 1e-9
    return bool(a == b)


def _agent_base(request: EvaluationRequest) -> dict[str, Any]:
    state: dict[str, Any] = {"user_input": truncate(request.input, 4000)}
    if request.trace and request.trace.tools:
        state["available_tools"] = tools_state(request.trace)
    return state


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class ToolSelection(Metric):
    """Whether the agent chose the right tools."""

    name = "tool_selection"
    display_name = "Tool Selection"
    category = "agent"
    description = (
        "Deterministic F1 between expected.tools and the tools actually called when ground "
        "truth exists; otherwise a yes/no judgment per call on whether the tool choice was "
        "appropriate."
    )
    primitives = ("binary",)
    deterministic_support = "partial"
    required_fields = ("input", "trace")
    optional_fields = ("expected",)
    default_threshold = 0.7

    def check(self, request: EvaluationRequest) -> DeterministicOutcome | None:
        calls = _calls(request)
        expected = request.expected.tools if request.expected else None
        if expected is None:
            if not calls and request.trace is not None and not request.trace.tools:
                return DeterministicOutcome(score=1.0, explanation="No tools were available or used.")
            return None
        used = [c.name for _, c in calls]
        exp, got = set(expected), set(used)
        if not exp and not got:
            return DeterministicOutcome(score=1.0, explanation="No tools expected and none used.")
        overlap = len(exp & got)
        precision = overlap / len(got) if got else 0.0
        recall = overlap / len(exp) if exp else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        steps = [
            _step(i, "expected_tool" if c.name in exp else "unexpected_tool", 1.0 if c.name in exp else 0.0)
            for i, c in calls
        ]
        return DeterministicOutcome(
            score=f1,
            explanation=f"Tool F1 {f1:.2f} (precision {precision:.2f}, recall {recall:.2f}).",
            details={
                "expected": sorted(exp),
                "used": used,
                "missing": sorted(exp - got),
                "unexpected": sorted(got - exp),
                "precision": precision,
                "recall": recall,
                "steps": steps,
            },
        )

    def rubric(self, request: EvaluationRequest) -> Rubric:
        calls = _calls(request)[:MAX_CALLS]
        state = _agent_base(request)
        if not calls:
            return Rubric(
                questions=[
                    BinaryQuestion(
                        id="no_tools",
                        instructions=(
                            "The agent answered without calling any tool. Could `user_input` be "
                            "handled well without any of `available_tools`?"
                        ),
                        true="Yes: no tool was needed.",
                        false="No: the agent should have used a tool.",
                    )
                ],
                state=state,
                aux={"steps": []},
            )
        state["tool_calls"] = {f"call_{k + 1}": call_state(c) for k, (_, c) in enumerate(calls)}
        questions = [
            BinaryQuestion(
                id=f"call_{k + 1}",
                instructions=(
                    f"Was the tool used in `tool_calls.call_{k + 1}` an appropriate choice for "
                    "making progress on `user_input`, given `available_tools`?"
                ),
                true="Appropriate: the right tool for this step.",
                false="Inappropriate: a different tool (or no tool) should have been used.",
            )
            for k in range(len(calls))
        ]
        return Rubric(questions=questions, state=state, aux={"steps": [i for i, _ in calls]})

    def aggregate(self, answers: dict[str, Answer], rubric: Rubric) -> Aggregation:
        base = super().aggregate(answers, rubric)
        steps = [
            _step(idx, "appropriate" if answers[f"call_{k + 1}"].score >= 0.5 else "inappropriate",
                  answers[f"call_{k + 1}"].score, answers[f"call_{k + 1}"].explanation)
            for k, idx in enumerate(rubric.aux["steps"])
        ]
        return base.model_copy(update={"details": {"steps": steps}})


class ToolArgumentsQuality(Metric):
    """Whether tool-call arguments are valid and correct."""

    name = "tool_arguments_quality"
    display_name = "Tool Arguments Quality"
    category = "agent"
    description = (
        "Validates arguments against each tool's JSON Schema (deterministic), compares with "
        "expected.tool_calls when provided, and otherwise grades each valid call's arguments "
        "on a 3-level scale."
    )
    primitives = ("score",)
    deterministic_support = "partial"
    required_fields = ("input", "trace")
    optional_fields = ("expected",)
    default_threshold = 0.7

    def not_applicable_reason(self, request: EvaluationRequest) -> str:
        return "the trace contains no tool calls"

    def _schema_errors(self, request: EvaluationRequest) -> list[list[str]]:
        trace = request.trace or AgentTrace()
        errors = []
        for _, call in _calls(request):
            spec = trace.tool_spec(call.name)
            if spec is None and trace.tools:
                errors.append([f"unknown tool '{call.name}'"])
            else:
                errors.append(validate_arguments(call.arguments, spec))
        return errors

    def check(self, request: EvaluationRequest) -> DeterministicOutcome | None:
        calls = _calls(request)
        if not calls:
            return None
        expected = request.expected.tool_calls if request.expected else None
        if expected:
            unused = list(range(len(calls)))
            scores: list[float] = []
            steps = []
            for exp in expected:
                match = next((p for p in unused if calls[p][1].name == exp.name), None)
                if match is None:
                    scores.append(0.0)
                    continue
                unused.remove(match)
                actual = calls[match][1].arguments
                keys = list(exp.arguments)
                ok = sum(1 for k in keys if k in actual and _values_equal(actual[k], exp.arguments[k]))
                score = ok / len(keys) if keys else 1.0
                scores.append(score)
                steps.append(_step(calls[match][0], "correct_arguments" if score == 1.0 else "wrong_arguments", score))
            mean = sum(scores) / len(scores)
            return DeterministicOutcome(
                score=mean,
                explanation=f"Arguments match expected.tool_calls with mean accuracy {mean:.2f}.",
                details={"per_expected_call": scores, "steps": steps},
            )
        errors = self._schema_errors(request)
        if all(errors):
            return DeterministicOutcome(
                score=0.0,
                explanation="Every tool call violates its tool's parameter schema.",
                details={
                    "schema_errors": errors,
                    "steps": [_step(i, "invalid_arguments", 0.0, "; ".join(e)) for (i, _), e in zip(calls, errors, strict=True)],
                },
            )
        return None

    def rubric(self, request: EvaluationRequest) -> Rubric | None:
        calls = _calls(request)
        if not calls:
            return None
        trace = request.trace or AgentTrace()
        errors = self._schema_errors(request)
        judged = [(pos, i, c) for pos, ((i, c), e) in enumerate(zip(calls, errors, strict=True)) if not e][:MAX_CALLS]
        state: dict[str, Any] = {"user_input": truncate(request.input, 4000)}
        if trace.tools:
            state["available_tools"] = tools_state(trace, with_schema=True)
        state["tool_calls"] = {f"call_{k + 1}": call_state(c) for k, (_, _, c) in enumerate(judged)}
        questions = [
            ScoreQuestion(
                id=f"call_{k + 1}",
                instructions=(
                    f"How correct and complete are the arguments in `tool_calls.call_{k + 1}` for "
                    "what the agent is trying to do for `user_input`? Use the tool's parameter "
                    "definition in `available_tools` when present."
                ),
                levels=[
                    "Wrong: arguments are missing, malformed, or would not accomplish the step.",
                    "Partially correct: right intent, but a value is wrong, imprecise or missing.",
                    "Correct: complete and accurately reflect the user's request and prior results.",
                ],
            )
            for k in range(len(judged))
        ]
        invalid = [(i, e) for (i, _), e in zip(calls, errors, strict=True) if e]
        return Rubric(
            questions=questions,
            state=state,
            aux={"judged_steps": [i for _, i, _ in judged], "invalid": invalid},
        )

    def aggregate(self, answers: dict[str, Answer], rubric: Rubric) -> Aggregation:
        judged: list[int] = rubric.aux["judged_steps"]
        invalid: list[tuple[int, list[str]]] = rubric.aux["invalid"]
        steps = [
            _step(idx, "good_arguments" if answers[f"call_{k + 1}"].score >= 0.5 else "weak_arguments",
                  answers[f"call_{k + 1}"].score, answers[f"call_{k + 1}"].explanation)
            for k, idx in enumerate(judged)
        ]
        steps += [_step(i, "invalid_arguments", 0.0, "; ".join(e)) for i, e in invalid]
        scores = [s["score"] for s in steps]
        return Aggregation(
            score=sum(scores) / len(scores) if scores else 0.0,
            details={"steps": sorted(steps, key=lambda s: s["step_index"]), "schema_errors": len(invalid)},
        )


class TrajectoryEfficiency(Metric):
    """Whether the agent reached its result without wasted steps."""

    name = "trajectory_efficiency"
    display_name = "Trajectory Efficiency"
    category = "agent"
    description = (
        "Deterministic min(1, expected.max_tool_calls / actual calls) when a budget is given; "
        "otherwise a 4-level judgment of the trajectory using code-computed facts "
        "(duplicate and failed calls)."
    )
    primitives = ("score",)
    deterministic_support = "partial"
    required_fields = ("input", "trace")
    optional_fields = ("expected",)
    default_threshold = 0.6

    def _facts(self, request: EvaluationRequest) -> dict[str, int]:
        calls = _calls(request)
        return {
            "steps": len(request.trace.steps) if request.trace else 0,
            "tool_calls": len(calls),
            "duplicate_calls": len(duplicate_indices(calls)),
            "failed_calls": sum(1 for _, c in calls if c.error),
        }

    def check(self, request: EvaluationRequest) -> DeterministicOutcome | None:
        budget = request.expected.max_tool_calls if request.expected else None
        if budget is None:
            return None
        facts = self._facts(request)
        n = facts["tool_calls"]
        score = 1.0 if n <= budget else budget / n
        return DeterministicOutcome(
            score=score,
            explanation=f"{n} tool call(s) against a budget of {budget}.",
            details={"facts": facts, "budget": budget},
        )

    def rubric(self, request: EvaluationRequest) -> Rubric:
        trace = request.trace or AgentTrace()
        state = _agent_base(request)
        state["trajectory"] = trajectory_state(trace)
        state["trajectory_facts"] = self._facts(request)
        if request.output:
            state["final_response"] = truncate(request.output, 2000)
        return Rubric(
            questions=[
                ScoreQuestion(
                    id="efficiency",
                    instructions=(
                        "How efficient is the agent trajectory in `trajectory` for accomplishing "
                        "`user_input`? Penalize redundant, repeated or irrelevant steps. "
                        "`trajectory_facts` contains counts computed by code."
                    ),
                    levels=[
                        "Very inefficient: loops, repeats calls, or wanders through many "
                        "irrelevant steps.",
                        "Inefficient: several unnecessary or repeated steps before the result.",
                        "Reasonably efficient: minor detours or a single redundant step.",
                        "Optimal: every step was needed and no obviously shorter path existed.",
                    ],
                )
            ],
            state=state,
        )

    def aggregate(self, answers: dict[str, Answer], rubric: Rubric) -> Aggregation:
        base = super().aggregate(answers, rubric)
        return base.model_copy(update={"details": {"facts": rubric.state["trajectory_facts"]}})


class TaskSuccess(Metric):
    """Whether the agent actually accomplished the user's goal."""

    name = "task_success"
    display_name = "Task Success"
    category = "agent"
    description = (
        "Deterministic match of the final output against expected.answer when provided; "
        "otherwise a yes/no judgment of goal completion using the final response and the "
        "evidence in the trajectory."
    )
    primitives = ("binary",)
    deterministic_support = "partial"
    required_fields = ("input",)
    optional_fields = ("output", "trace", "expected")
    default_threshold = 0.5

    def missing_fields(self, request: EvaluationRequest) -> list[str]:
        missing = super().missing_fields(request)
        if not request.has("output") and not request.has("trace"):
            missing.append("output or trace")
        return missing

    def check(self, request: EvaluationRequest) -> DeterministicOutcome | None:
        refs = request.expected.answers() if request.expected else []
        if refs and request.output and matches_reference(request.output, refs, "contains"):
            return DeterministicOutcome(score=1.0, explanation="The final output contains the expected answer.")
        return None

    def rubric(self, request: EvaluationRequest) -> Rubric:
        state = _agent_base(request)
        if request.output:
            state["final_response"] = truncate(request.output, 3000)
        if request.trace:
            state["trajectory"] = trajectory_state(request.trace)
        refs = request.expected.answers() if request.expected else []
        if refs:
            state["reference_outcome"] = refs[0] if len(refs) == 1 else refs
        return Rubric(
            questions=[
                BinaryQuestion(
                    id="success",
                    instructions=(
                        "Did the agent accomplish the goal in `user_input`? Judge by "
                        "`final_response` and the tool results in `trajectory`"
                        + (" and compare with `reference_outcome`" if refs else "")
                        + ". Claims of success that the trajectory does not support do not count."
                    ),
                    true="Accomplished: the user got what they asked for, or the requested "
                    "action was actually performed.",
                    false="Not accomplished: failed, only partially done, or success is "
                    "claimed without evidence.",
                )
            ],
            state=state,
        )


class UnnecessaryToolCalls(Metric):
    """Share of tool calls that were necessary (1.0 = no wasted calls)."""

    name = "unnecessary_tool_calls"
    display_name = "Unnecessary Tool Calls"
    category = "agent"
    description = (
        "Duplicate calls are always unnecessary (deterministic). With expected.tools, calls to "
        "unexpected tools are unnecessary too; otherwise each remaining call gets a yes/no "
        "necessity judgment. Score = share of necessary calls."
    )
    primitives = ("binary",)
    deterministic_support = "partial"
    required_fields = ("input", "trace")
    optional_fields = ("expected",)
    default_threshold = 0.7

    def check(self, request: EvaluationRequest) -> DeterministicOutcome | None:
        calls = _calls(request)
        if not calls:
            return DeterministicOutcome(score=1.0, explanation="No tool calls were made.")
        dups = duplicate_indices(calls)
        expected = request.expected.tools if request.expected else None
        if expected is None and len(dups) < len(calls):
            return None
        unnecessary = set(dups)
        if expected is not None:
            unnecessary |= {pos for pos, (_, c) in enumerate(calls) if c.name not in expected}
        steps = [
            _step(i, "duplicate" if pos in dups else "unnecessary" if pos in unnecessary else "necessary",
                  0.0 if pos in unnecessary else 1.0)
            for pos, (i, _) in enumerate(calls)
        ]
        score = 1.0 - len(unnecessary) / len(calls)
        return DeterministicOutcome(
            score=score,
            explanation=f"{len(unnecessary)} of {len(calls)} tool call(s) were unnecessary.",
            details={"unnecessary": len(unnecessary), "duplicates": len(dups), "steps": steps},
        )

    def rubric(self, request: EvaluationRequest) -> Rubric:
        calls = _calls(request)
        dups = duplicate_indices(calls)
        judged = [(pos, i, c) for pos, (i, c) in enumerate(calls) if pos not in dups][:MAX_CALLS]
        state = _agent_base(request)
        state["tool_calls"] = {f"call_{k + 1}": call_state(c) for k, (_, _, c) in enumerate(judged)}
        questions = [
            BinaryQuestion(
                id=f"call_{k + 1}",
                instructions=(
                    f"Was the call in `tool_calls.call_{k + 1}` necessary to accomplish "
                    "`user_input`? A call is unnecessary if its result was not needed or the "
                    "information was already available."
                ),
                true="Necessary: the call contributed to accomplishing the task.",
                false="Unnecessary: the task could be accomplished just as well without it.",
            )
            for k in range(len(judged))
        ]
        return Rubric(
            questions=questions,
            state=state,
            aux={"judged_steps": [i for _, i, _ in judged], "duplicate_steps": [calls[p][0] for p in sorted(dups)]},
        )

    def aggregate(self, answers: dict[str, Answer], rubric: Rubric) -> Aggregation:
        judged: list[int] = rubric.aux["judged_steps"]
        duplicates: list[int] = rubric.aux["duplicate_steps"]
        steps = [
            _step(idx, "necessary" if answers[f"call_{k + 1}"].score >= 0.5 else "unnecessary",
                  answers[f"call_{k + 1}"].score, answers[f"call_{k + 1}"].explanation)
            for k, idx in enumerate(judged)
        ]
        steps += [_step(i, "duplicate", 0.0, "Identical to an earlier call.") for i in duplicates]
        total = len(judged) + len(duplicates)
        necessary = sum(answers[f"call_{k + 1}"].score for k in range(len(judged)))
        return Aggregation(
            score=necessary / total if total else 1.0,
            details={"steps": sorted(steps, key=lambda s: s["step_index"]), "duplicates": len(duplicates)},
        )
