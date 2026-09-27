"""Evaluator registry: resolves evaluator names used by policies to instances.

Built-in names:

* ``deterministic`` — :class:`DeterministicEvaluator`
* ``jev`` — :class:`JevEvaluator` (needs ``OPENROUTER_API_KEY``)
* ``llm`` — the configured generative judge (OpenRouter by default, or any OpenAI-compatible
  endpoint via ``EVALCASCADE_JUDGE_BASE_URL``)
* ``openrouter`` — :class:`OpenRouterLLMJudge` explicitly

Custom evaluators can be registered under any name and referenced from a policy.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from evalcascade.config import Settings
from evalcascade.core.evaluator import Evaluator
from evalcascade.errors import ConfigurationError
from evalcascade.evaluators.deterministic import DeterministicEvaluator
from evalcascade.evaluators.jev import JevEvaluator
from evalcascade.evaluators.llm_judge import LLMJudge, OpenRouterLLMJudge

BUILTIN_EVALUATORS = ("deterministic", "jev", "llm", "openrouter")


class EvaluatorRegistry:
    """Lazily builds built-in evaluators from :class:`Settings`; holds custom ones."""

    def __init__(
        self, settings: Settings | None = None, evaluators: Mapping[str, Evaluator] | None = None
    ) -> None:
        self._settings = settings
        self._evaluators: dict[str, Evaluator] = dict(evaluators or {})
        self._owned: set[str] = set()
        self._evaluators.setdefault("deterministic", DeterministicEvaluator())

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = Settings.load()
        return self._settings

    @property
    def deterministic(self) -> DeterministicEvaluator:
        det = self._evaluators["deterministic"]
        if not isinstance(det, DeterministicEvaluator):
            raise ConfigurationError(
                "the 'deterministic' evaluator must be a DeterministicEvaluator"
            )
        return det

    def register(self, name: str, evaluator: Evaluator) -> None:
        self._evaluators[name] = evaluator

    def names(self) -> list[str]:
        return sorted(set(self._evaluators) | set(BUILTIN_EVALUATORS))

    def get(self, name: str) -> Evaluator:
        if name in self._evaluators:
            return self._evaluators[name]
        evaluator: Evaluator
        match name:
            case "jev":
                evaluator = JevEvaluator.from_settings(self.settings)
            case "llm":
                evaluator = LLMJudge.from_settings(self.settings, name="llm")
            case "openrouter":
                evaluator = OpenRouterLLMJudge.from_settings(self.settings, name="openrouter")
            case _:
                raise ConfigurationError(
                    f"unknown evaluator {name!r}; available: {', '.join(self.names())}"
                )
        self._evaluators[name] = evaluator
        self._owned.add(name)
        return evaluator

    def check(self, names: Iterable[str]) -> list[str]:
        """Return human-readable problems for evaluators that are not usable."""
        problems = []
        for name in sorted(set(names)):
            try:
                ok, reason = self.get(name).available()
            except ConfigurationError as exc:
                problems.append(str(exc))
                continue
            if not ok:
                problems.append(f"{name}: {reason}")
        return problems

    def describe(self, names: Iterable[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name in sorted(set(names)):
            try:
                out[name] = self.get(name).describe()
            except ConfigurationError as exc:
                out[name] = {"name": name, "error": str(exc)}
        return out

    async def aclose(self) -> None:
        for evaluator in self._evaluators.values():
            await evaluator.aclose()
