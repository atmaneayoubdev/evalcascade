"""First-class metrics. Every metric normalizes to a score in [0, 1].

General: AnswerRelevance, Correctness, TaskCompletion, Safety
RAG: Groundedness, ContextRelevance, CitationPresence, CitationCorrectness
Agents: ToolSelection, ToolArgumentsQuality, TrajectoryEfficiency, TaskSuccess,
UnnecessaryToolCalls
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from evalcascade.core.metric import Aggregation, DeterministicOutcome, Metric, MetricInfo
from evalcascade.errors import ConfigurationError
from evalcascade.metrics.agent import (
    TaskSuccess,
    ToolArgumentsQuality,
    ToolSelection,
    TrajectoryEfficiency,
    UnnecessaryToolCalls,
)
from evalcascade.metrics.general import AnswerRelevance, Correctness, Safety, TaskCompletion
from evalcascade.metrics.rag import (
    CitationCorrectness,
    CitationPresence,
    ContextRelevance,
    Groundedness,
)

METRICS: dict[str, type[Metric]] = {
    cls.name: cls
    for cls in (
        AnswerRelevance,
        Correctness,
        TaskCompletion,
        Safety,
        Groundedness,
        ContextRelevance,
        CitationPresence,
        CitationCorrectness,
        ToolSelection,
        ToolArgumentsQuality,
        TrajectoryEfficiency,
        TaskSuccess,
        UnnecessaryToolCalls,
    )
}

#: Named metric bundles used by the CLI (``evalcascade run --suite rag``).
SUITES: dict[str, tuple[str, ...]] = {
    "general": ("answer_relevance", "correctness", "task_completion", "safety"),
    "rag": ("answer_relevance", "groundedness", "context_relevance", "citation_presence"),
    "agent": (
        "task_success",
        "tool_selection",
        "tool_arguments_quality",
        "trajectory_efficiency",
        "unnecessary_tool_calls",
    ),
}


def get_metric(name: str, **params: Any) -> Metric:
    """Instantiate a metric by its registry name."""
    try:
        cls = METRICS[name]
    except KeyError:
        raise ConfigurationError(
            f"unknown metric {name!r}; available: {', '.join(sorted(METRICS))}"
        ) from None
    try:
        return cls(**params)
    except ValueError as exc:
        raise ConfigurationError(f"invalid parameters for {name}: {exc}") from exc


def build_metrics(
    names: Iterable[str], params: Mapping[str, Mapping[str, Any]] | None = None
) -> list[Metric]:
    """Instantiate metrics by name (suite names are expanded), applying per-metric params."""
    params = params or {}
    expanded: list[str] = []
    for name in names:
        for item in SUITES.get(name, (name,)):
            if item not in expanded:
                expanded.append(item)
    return [get_metric(n, **dict(params.get(n, {}))) for n in expanded]


def metric_catalog() -> list[MetricInfo]:
    return [cls.info() for cls in METRICS.values()]


__all__ = [
    "METRICS",
    "SUITES",
    "Aggregation",
    "AnswerRelevance",
    "CitationCorrectness",
    "CitationPresence",
    "ContextRelevance",
    "Correctness",
    "DeterministicOutcome",
    "Groundedness",
    "Metric",
    "MetricInfo",
    "Safety",
    "TaskCompletion",
    "TaskSuccess",
    "ToolArgumentsQuality",
    "ToolSelection",
    "TrajectoryEfficiency",
    "UnnecessaryToolCalls",
    "build_metrics",
    "get_metric",
    "metric_catalog",
]
