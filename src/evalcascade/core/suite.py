"""The user-facing evaluation suite.

.. code-block:: python

    from evalcascade import EvalSuite
    from evalcascade.metrics import AnswerRelevance, Groundedness

    suite = EvalSuite(metrics=[AnswerRelevance(), Groundedness()])
    result = await suite.evaluate(input="...", output="...", context=["..."])
    print(result.overall_score)

    experiment = await suite.run("datasets/rag_qa.jsonl", name="baseline")
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Coroutine, Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from evalcascade.config import Settings
from evalcascade.core.evaluator import Evaluator
from evalcascade.core.metric import Metric
from evalcascade.core.policy import EvaluationPolicy
from evalcascade.core.results import CaseResult, EvaluationResult
from evalcascade.core.runtime import CascadeRuntime
from evalcascade.core.types import AgentTrace, EvaluationRequest, Expected
from evalcascade.datasets.dataset import Case, Dataset
from evalcascade.errors import ConfigurationError
from evalcascade.evaluators.registry import EvaluatorRegistry
from evalcascade.experiments.experiment import DatasetRef, Experiment
from evalcascade.experiments.summary import summarize
from evalcascade.redaction import redact

if TYPE_CHECKING:
    from evalcascade.storage.store import ExperimentStore

T = TypeVar("T")
TaskOutput = str | Mapping[str, Any] | None
Task = Callable[[Case], TaskOutput | Awaitable[TaskOutput]]
ResultCallback = Callable[[CaseResult], None]


class EvaluationSuite:
    """A set of metrics evaluated through the cascade."""

    def __init__(
        self,
        metrics: Sequence[Metric],
        *,
        policy: EvaluationPolicy | None = None,
        evaluators: Mapping[str, Evaluator] | None = None,
        settings: Settings | None = None,
        name: str | None = None,
        concurrency: int = 8,
    ) -> None:
        if not metrics:
            raise ConfigurationError("an evaluation suite needs at least one metric")
        keys = [m.key for m in metrics]
        dups = sorted({k for k in keys if keys.count(k) > 1})
        if dups:
            raise ConfigurationError(
                f"duplicate metric keys {dups}; set alias= to use a metric twice"
            )
        self.metrics = list(metrics)
        self.name = name
        self.concurrency = max(1, concurrency)
        self.registry = EvaluatorRegistry(settings, evaluators)
        self.policy = policy if policy is not None else self.registry.settings.policy
        self.runtime = CascadeRuntime(self.registry, self.policy)
        self._preflight_done = False

    @property
    def settings(self) -> Settings:
        return self.registry.settings

    # -- configuration ------------------------------------------------------------------

    def evaluator_names(self) -> set[str]:
        names: set[str] = set()
        for metric in self.metrics:
            if metric.deterministic_support == "full":
                continue
            resolved = self.policy.resolve(metric)
            names.update(n for n in (resolved.primary, resolved.fallback) if n)
        return names

    def preflight(self) -> None:
        """Fail fast if an evaluator the policy needs is not usable (e.g. missing API key)."""
        if self._preflight_done:
            return
        problems = self.registry.check(self.evaluator_names())
        if problems:
            raise ConfigurationError(
                "cannot evaluate with the current policy:\n  - "
                + "\n  - ".join(problems)
                + "\nSet the missing API key(s), or use a policy that does not need them "
                "(e.g. EvaluationPolicy.deterministic_only() / --policy deterministic)."
            )
        self._preflight_done = True

    def config(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "metrics": [m.config() for m in self.metrics],
            "policy": self.policy.model_dump(),
            "evaluators": self.registry.describe({"deterministic", *self.evaluator_names()}),
        }

    # -- single evaluations ---------------------------------------------------------------

    async def evaluate(
        self,
        input: str | None = None,
        output: str | None = None,
        context: Sequence[str] | str | None = None,
        expected: Expected | Mapping[str, Any] | str | None = None,
        trace: AgentTrace | Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        *,
        id: str | None = None,
        request: EvaluationRequest | None = None,
    ) -> EvaluationResult:
        """Evaluate one interaction with every metric in the suite."""
        if request is None:
            request = EvaluationRequest.model_validate(
                {
                    "id": id,
                    "input": input,
                    "output": output,
                    "context": context,
                    "expected": expected,
                    "trace": trace,
                    "metadata": dict(metadata or {}),
                }
            )
        self.preflight()
        return await self.runtime.evaluate(self.metrics, request)

    def evaluate_sync(self, *args: Any, **kwargs: Any) -> EvaluationResult:
        """Synchronous :meth:`evaluate` for scripts and notebooks without an event loop."""
        return self._run_sync(self.evaluate(*args, **kwargs))

    async def evaluate_many(
        self,
        requests: Iterable[EvaluationRequest],
        *,
        concurrency: int | None = None,
        on_result: Callable[[EvaluationResult], None] | None = None,
    ) -> list[EvaluationResult]:
        """Evaluate several requests concurrently; results keep the input order."""
        self.preflight()
        semaphore = asyncio.Semaphore(concurrency or self.concurrency)

        async def one(request: EvaluationRequest) -> EvaluationResult:
            async with semaphore:
                result = await self.runtime.evaluate(self.metrics, request)
            if on_result is not None:
                on_result(result)
            return result

        return list(await asyncio.gather(*(one(r) for r in requests)))

    # -- datasets / experiments -------------------------------------------------------------

    async def run(
        self,
        dataset: Dataset | str | Path | Sequence[Mapping[str, Any]],
        *,
        name: str | None = None,
        task: Task | None = None,
        concurrency: int | None = None,
        limit: int | None = None,
        tags: Sequence[str] = (),
        notes: str | None = None,
        is_demo: bool = False,
        store: ExperimentStore | None = None,
        on_result: ResultCallback | None = None,
    ) -> Experiment:
        """Evaluate a dataset and return an :class:`Experiment` (saved if ``store`` is given).

        ``task`` optionally generates outputs on the fly: it receives each case and returns
        the output string, or a mapping with any of ``output``, ``context``, ``trace``.
        """
        ds = _as_dataset(dataset)
        cases = ds.cases[:limit] if limit else list(ds.cases)
        self.preflight()
        semaphore = asyncio.Semaphore(concurrency or self.concurrency)

        async def one(case: Case) -> CaseResult:
            async with semaphore:
                try:
                    prepared = await _apply_task(task, case) if task else case
                except Exception as exc:
                    result = CaseResult(
                        case_id=case.id,
                        case=case,
                        error=redact(f"task failed: {type(exc).__name__}: {exc}"),
                    )
                else:
                    evaluated = await self.runtime.evaluate(self.metrics, prepared)
                    result = CaseResult(**evaluated.model_dump(), case=prepared)
            if on_result is not None:
                on_result(result)
            return result

        results = list(await asyncio.gather(*(one(c) for c in cases)))
        config = self.config()
        experiment = Experiment(
            name=name or self.name or f"{ds.name}-run",
            dataset=DatasetRef(
                name=ds.name, hash=ds.hash, size=len(cases), path=str(ds.path) if ds.path else None
            ),
            metrics=config["metrics"],
            policy=config["policy"],
            evaluators=config["evaluators"],
            summary=summarize(results),
            results=results,
            is_demo=is_demo,
            tags=list(tags),
            notes=notes,
        )
        if store is not None:
            store.save_experiment(experiment)
        return experiment

    def run_sync(self, *args: Any, **kwargs: Any) -> Experiment:
        """Synchronous :meth:`run`."""
        return self._run_sync(self.run(*args, **kwargs))

    # -- lifecycle -----------------------------------------------------------------------------

    async def aclose(self) -> None:
        await self.registry.aclose()

    async def __aenter__(self) -> EvaluationSuite:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def _run_sync(self, coro: Coroutine[Any, Any, T]) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            coro.close()
            raise RuntimeError(
                "an event loop is already running; use `await suite.evaluate(...)` / "
                "`await suite.run(...)` instead of the *_sync helpers"
            )

        async def wrapped() -> T:
            try:
                return await coro
            finally:
                await self.aclose()  # network clients are bound to this event loop

        return asyncio.run(wrapped())


EvalSuite = EvaluationSuite


def _as_dataset(dataset: Dataset | str | Path | Sequence[Mapping[str, Any]]) -> Dataset:
    if isinstance(dataset, Dataset):
        return dataset
    if isinstance(dataset, str | Path):
        return Dataset.from_jsonl(dataset)
    return Dataset.from_records([dict(r) for r in dataset], name="inline")


async def _apply_task(task: Task, case: Case) -> Case:
    produced = task(case)
    if inspect.isawaitable(produced):
        produced = await produced
    if produced is None:
        return case
    if isinstance(produced, str):
        return case.model_copy(update={"output": produced})
    updates = {
        k: v for k, v in dict(produced).items() if k in {"output", "context", "trace", "metadata"}
    }
    return Case.model_validate({**case.model_dump(), **updates})
