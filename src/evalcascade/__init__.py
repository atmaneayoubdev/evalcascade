"""EvalCascade — adaptive evaluation for LLM, RAG and agentic systems.

System One judges first. LLMs only when necessary.
"""

from evalcascade._version import __version__
from evalcascade.config import Settings
from evalcascade.core.metric import DeterministicOutcome, Metric
from evalcascade.core.policy import EvaluationPolicy, MetricPolicy
from evalcascade.core.results import CaseResult, EvaluationResult, Judgment, MetricResult
from evalcascade.core.rubric import BinaryQuestion, ChoiceQuestion, Rubric, ScoreQuestion
from evalcascade.core.suite import EvalSuite, EvaluationSuite
from evalcascade.core.types import AgentTrace, EvaluationRequest, ToolCall, ToolSpec, TraceStep
from evalcascade.datasets import Case, Dataset, load_dataset
from evalcascade.errors import ConfigurationError, EvalCascadeError, ProviderError
from evalcascade.experiments import Comparison, Experiment, compare_experiments
from evalcascade.regression import GateResult, RegressionGate

__all__ = [
    "AgentTrace",
    "BinaryQuestion",
    "Case",
    "CaseResult",
    "ChoiceQuestion",
    "Comparison",
    "ConfigurationError",
    "Dataset",
    "DeterministicOutcome",
    "EvalCascadeError",
    "EvalSuite",
    "EvaluationPolicy",
    "EvaluationRequest",
    "EvaluationResult",
    "EvaluationSuite",
    "Experiment",
    "GateResult",
    "Judgment",
    "Metric",
    "MetricPolicy",
    "MetricResult",
    "ProviderError",
    "RegressionGate",
    "Rubric",
    "ScoreQuestion",
    "Settings",
    "ToolCall",
    "ToolSpec",
    "TraceStep",
    "__version__",
    "compare_experiments",
    "load_dataset",
]
