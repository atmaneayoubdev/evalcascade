"""Evaluator backends: deterministic, Jev (System One), LLM judges, and a demo simulator."""

from evalcascade.core.evaluator import EvalItem, Evaluator, RawAnswers, SemanticEvaluator
from evalcascade.evaluators.deterministic import DeterministicEvaluator
from evalcascade.evaluators.jev import JevEvaluator
from evalcascade.evaluators.llm_judge import LLMJudge, OpenRouterLLMJudge
from evalcascade.evaluators.registry import BUILTIN_EVALUATORS, EvaluatorRegistry
from evalcascade.evaluators.simulated import SimulatedEvaluator

__all__ = [
    "BUILTIN_EVALUATORS",
    "DeterministicEvaluator",
    "EvalItem",
    "Evaluator",
    "EvaluatorRegistry",
    "JevEvaluator",
    "LLMJudge",
    "OpenRouterLLMJudge",
    "RawAnswers",
    "SemanticEvaluator",
    "SimulatedEvaluator",
]
