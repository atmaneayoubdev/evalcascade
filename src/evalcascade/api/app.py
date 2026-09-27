"""Local FastAPI server: evaluation, datasets, experiments, comparison, gates, dashboard.

Start with ``evalcascade serve``. OpenAPI docs are served at ``/docs``. The server binds to
127.0.0.1 by default; set ``EVALCASCADE_API_TOKEN`` to require a bearer token when exposing it.
"""

from __future__ import annotations

import hmac
import statistics
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from evalcascade._version import __version__
from evalcascade.api.schemas import (
    DatasetDetail,
    DatasetUpload,
    EvaluateRequest,
    ExperimentDetail,
    GateRequest,
    Health,
    MetricSpec,
    Overview,
    OverviewAverages,
    OverviewTotals,
    Page,
    RegressionIndicator,
    TrendPoint,
)
from evalcascade.api.static import find_dashboard
from evalcascade.config import Settings
from evalcascade.core.metric import Metric, MetricInfo
from evalcascade.core.policy import EvaluationPolicy
from evalcascade.core.results import CaseResult, EvaluationResult
from evalcascade.core.suite import EvaluationSuite
from evalcascade.datasets.dataset import Dataset
from evalcascade.errors import ConfigurationError, DatasetError, EvalCascadeError, NotFoundError
from evalcascade.experiments.compare import Comparison, compare_experiments
from evalcascade.experiments.summary import RouteCounts
from evalcascade.metrics import SUITES, build_metrics, get_metric, metric_catalog
from evalcascade.regression.gate import GateResult, RegressionGate
from evalcascade.storage.store import (
    CaseResultRow,
    DatasetInfo,
    ExperimentListItem,
    ExperimentStore,
)

REGRESSION_DROP = 0.03
METRIC_REGRESSION_DROP = 0.05


def create_app(settings: Settings | None = None, store: ExperimentStore | None = None) -> FastAPI:
    """Application factory (used by ``evalcascade serve`` and tests)."""
    settings = settings or Settings.load()
    store = store or ExperimentStore.from_settings(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        store.dispose()

    app = FastAPI(
        title="EvalCascade API",
        version=__version__,
        description="Adaptive evaluation for LLM, RAG and agentic systems — System One judges "
        "first, LLMs only when necessary.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    async def require_token(request: Request) -> None:
        token = settings.api_token
        if token is None:
            return
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), token.get_secret_value().encode()):
            raise HTTPException(status_code=401, detail="missing or invalid bearer token")

    auth = [Depends(require_token)]

    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(EvalCascadeError)
    async def _bad_request(_: Request, exc: EvalCascadeError) -> JSONResponse:
        status = 400 if isinstance(exc, ConfigurationError | DatasetError) else 502
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    # -- health / config / metrics ----------------------------------------------------------

    @app.get("/api/health", response_model=Health, tags=["system"])
    def health() -> Health:
        ok = store.ping()
        return Health(
            status="ok" if ok else "degraded", version=__version__, database="ok" if ok else "error"
        )

    @app.get("/api/config", dependencies=auth, tags=["system"])
    def config() -> dict[str, Any]:
        """Effective configuration. Never includes secrets — only whether keys are set."""
        return settings.summary()

    @app.get("/api/metrics", response_model=list[MetricInfo], tags=["metrics"])
    def metrics() -> list[MetricInfo]:
        return metric_catalog()

    @app.get("/api/metrics/suites", tags=["metrics"])
    def metric_suites() -> dict[str, list[str]]:
        return {k: list(v) for k, v in SUITES.items()}

    # -- evaluation -------------------------------------------------------------------------------

    @app.post(
        "/api/evaluate", response_model=EvaluationResult, dependencies=auth, tags=["evaluation"]
    )
    async def evaluate(body: EvaluateRequest) -> EvaluationResult:
        names: list[str] = []
        specs: list[Metric] = []
        for item in body.metrics:
            if isinstance(item, MetricSpec):
                specs.append(get_metric(item.name, **item.params))
            else:
                names.append(item)
        metric_objs = [*build_metrics(names, settings.metrics), *specs]
        if not metric_objs:
            raise ConfigurationError("at least one metric is required")
        if body.policy is not None:
            policy = EvaluationPolicy.preset(body.policy, body.escalate_below)
        else:
            policy = settings.policy
            if body.escalate_below is not None:
                policy = policy.model_copy(update={"escalate_below": body.escalate_below})
        async with EvaluationSuite(metric_objs, policy=policy, settings=settings) as suite:
            return await suite.evaluate(
                input=body.input,
                output=body.output,
                context=body.context,
                expected=body.expected,
                trace=body.trace,
                metadata=body.metadata,
            )

    # -- datasets ---------------------------------------------------------------------------------

    @app.get(
        "/api/datasets", response_model=list[DatasetInfo], dependencies=auth, tags=["datasets"]
    )
    def list_datasets() -> list[DatasetInfo]:
        return store.list_datasets()

    @app.post(
        "/api/datasets",
        response_model=DatasetInfo,
        status_code=201,
        dependencies=auth,
        tags=["datasets"],
    )
    def upload_dataset(body: DatasetUpload) -> DatasetInfo:
        dataset = Dataset.from_records(body.cases, name=body.name, description=body.description)
        return store.register_dataset(
            dataset, description=body.description, overwrite=body.overwrite
        )

    @app.get(
        "/api/datasets/{name}", response_model=DatasetDetail, dependencies=auth, tags=["datasets"]
    )
    def get_dataset(
        name: str,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> DatasetDetail:
        info = store.get_dataset_info(name)
        dataset = store.load_dataset(name)
        cases = [c.model_dump(mode="json") for c in dataset.cases[offset : offset + limit]]
        return DatasetDetail(
            dataset=info, cases=Page(total=len(dataset), limit=limit, offset=offset, items=cases)
        )

    # -- experiments ------------------------------------------------------------------------------

    @app.get(
        "/api/experiments",
        response_model=list[ExperimentListItem],
        dependencies=auth,
        tags=["experiments"],
    )
    def list_experiments(
        include_demo: bool = True,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        name: str | None = None,
    ) -> list[ExperimentListItem]:
        return store.list_experiments(include_demo=include_demo, limit=limit, name=name)

    @app.get(
        "/api/experiments/{ref}",
        response_model=ExperimentDetail,
        dependencies=auth,
        tags=["experiments"],
    )
    def get_experiment(ref: str) -> ExperimentDetail:
        return ExperimentDetail.of(store.get_experiment(ref, with_results=False))

    @app.delete("/api/experiments/{ref}", dependencies=auth, tags=["experiments"])
    def delete_experiment(ref: str) -> dict[str, str]:
        return {"deleted": store.delete_experiment(ref)}

    @app.get("/api/experiments/{ref}/cases", dependencies=auth, tags=["experiments"])
    def list_cases(
        ref: str,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        filter: Literal["all", "passed", "failed", "escalated"] = "all",
    ) -> dict[str, Any]:
        total, rows = store.case_rows(ref, limit=limit, offset=offset, filter=filter)
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [r.model_dump(mode="json") for r in rows],
        }

    @app.get(
        "/api/experiments/{ref}/cases/{case_id}",
        response_model=CaseResult,
        dependencies=auth,
        tags=["experiments"],
    )
    def get_case(ref: str, case_id: str) -> CaseResult:
        return store.get_case(ref, case_id)

    @app.get("/api/compare", response_model=Comparison, dependencies=auth, tags=["experiments"])
    def compare(baseline: str, candidate: str) -> Comparison:
        return compare_experiments(store.get_experiment(baseline), store.get_experiment(candidate))

    @app.post("/api/gate", response_model=GateResult, dependencies=auth, tags=["experiments"])
    def gate(body: GateRequest) -> GateResult:
        regression_gate = RegressionGate(**body.model_dump(exclude={"baseline", "candidate"}))
        return regression_gate.evaluate(
            store.get_experiment(body.baseline), store.get_experiment(body.candidate)
        )

    # -- overview ---------------------------------------------------------------------------------

    @app.get("/api/overview", response_model=Overview, dependencies=auth, tags=["experiments"])
    def overview(include_demo: bool = True) -> Overview:
        items = store.list_experiments(include_demo=include_demo, limit=500)
        return build_overview(
            items,
            has_real=store.count_experiments(include_demo=False) > 0,
            has_demo=store.count_experiments() > store.count_experiments(include_demo=False),
        )

    # -- dashboard ------------------------------------------------------------

    dashboard = find_dashboard()
    if dashboard is not None:
        app.mount("/", StaticFiles(directory=dashboard, html=True), name="dashboard")
    else:

        @app.get("/", include_in_schema=False)
        def root() -> dict[str, str]:
            return {
                "name": "EvalCascade API",
                "version": __version__,
                "docs": "/docs",
                "dashboard": "not built — see web/README.md",
            }

    _ = CaseResultRow  # re-exported for OpenAPI consumers
    return app


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.fmean(clean) if clean else None


def build_overview(items: list[ExperimentListItem], *, has_real: bool, has_demo: bool) -> Overview:
    """Aggregate experiment summaries for the dashboard overview (newest-first input)."""
    routing = RouteCounts()
    for item in items:
        for m in item.summary.metrics.values():
            for field in ("deterministic", "jev", "llm", "jev_to_llm", "none"):
                setattr(routing, field, getattr(routing, field) + getattr(m.routes, field))

    by_name: dict[str, list[ExperimentListItem]] = {}
    for item in items:
        by_name.setdefault(item.name, []).append(item)
    regressions = []
    for name, runs in by_name.items():
        if len(runs) < 2:
            continue
        latest, previous = runs[0], runs[1]
        a, b = previous.summary.overall_score, latest.summary.overall_score
        delta = None if a is None or b is None else b - a
        metric_drop = any(
            (pm.mean or 0) - (latest.summary.metrics[k].mean or 0) > METRIC_REGRESSION_DROP
            for k, pm in previous.summary.metrics.items()
            if k in latest.summary.metrics
            and pm.mean is not None
            and latest.summary.metrics[k].mean is not None
        )
        regressions.append(
            RegressionIndicator(
                name=name,
                baseline_id=previous.id,
                candidate_id=latest.id,
                delta_overall=delta,
                regressed=(delta is not None and delta < -REGRESSION_DROP) or metric_drop,
                is_demo=latest.is_demo,
            )
        )

    recent_window = items[:30]
    return Overview(
        has_real_data=has_real,
        has_demo_data=has_demo,
        totals=OverviewTotals(
            experiments=len(items),
            cases=sum(i.summary.num_cases for i in items),
            evaluations=sum(i.summary.num_evaluations for i in items),
            cost_usd=sum(i.summary.cost_usd for i in items),
        ),
        averages=OverviewAverages(
            overall_score=_mean([i.summary.overall_score for i in recent_window]),
            pass_rate=_mean([i.summary.pass_rate for i in recent_window]),
            jev_acceptance_rate=_mean(
                [i.summary.routing.jev_acceptance_rate for i in recent_window]
            ),
            escalation_rate=_mean([i.summary.routing.escalation_rate for i in recent_window]),
            latency_p50_ms=_mean([i.summary.latency_ms.p50 for i in recent_window]),
        ),
        routing=routing,
        recent=items[:10],
        trend=[
            TrendPoint(
                id=i.id,
                name=i.name,
                created_at=i.created_at,
                overall_score=i.summary.overall_score,
                pass_rate=i.summary.pass_rate,
                cost_usd=i.summary.cost_usd,
                escalation_rate=i.summary.routing.escalation_rate,
                jev_acceptance_rate=i.summary.routing.jev_acceptance_rate,
                is_demo=i.is_demo,
            )
            for i in reversed(items[:30])
        ],
        regressions=regressions,
    )
