"""Local persistence for datasets and experiments (SQLite by default).

Experiment references accepted everywhere (CLI, API, SDK):

* a full experiment id (``3f9c2a1b7d4e``) or a unique id prefix (``3f9c``)
* an experiment name — resolves to the most recent experiment with that name
* ``latest`` — the most recent experiment; ``latest~1`` the one before it
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, delete, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from evalcascade.config import Settings
from evalcascade.core.results import CaseResult
from evalcascade.datasets.dataset import Dataset
from evalcascade.errors import DatasetError, NotFoundError
from evalcascade.experiments.experiment import DatasetRef, Experiment
from evalcascade.experiments.summary import ExperimentSummary
from evalcascade.storage.models import (
    SCHEMA_VERSION,
    Base,
    CaseResultRecord,
    DatasetRecord,
    ExperimentRecord,
    MetaRecord,
)

CaseFilter = Literal["all", "passed", "failed", "escalated"]


class DatasetInfo(BaseModel):
    name: str
    path: str | None = None
    description: str | None = None
    num_cases: int
    hash: str
    created_at: datetime
    fields: dict[str, int] = Field(default_factory=dict)


class ExperimentListItem(BaseModel):
    id: str
    name: str
    created_at: datetime
    dataset_name: str | None = None
    is_demo: bool = False
    tags: list[str] = Field(default_factory=list)
    summary: ExperimentSummary


class MetricCell(BaseModel):
    score: float | None
    passed: bool | None
    route: str
    status: str


class CaseResultRow(BaseModel):
    case_id: str
    input_preview: str
    overall_score: float | None
    passed: bool | None
    latency_ms: float
    cost_usd: float
    escalations: int
    has_trace: bool
    metrics: dict[str, MetricCell]


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _naive(dt: datetime) -> datetime:
    return _utc(dt).replace(tzinfo=None)


class ExperimentStore:
    """Datasets registry + experiment tracking on top of SQLAlchemy."""

    def __init__(self, url: str, *, home: Path | None = None) -> None:
        self.url = url
        self.home = home
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            db_path = url.split("sqlite:///", 1)[-1]
            if db_path and db_path != ":memory:" and not url.startswith("sqlite:///:memory:"):
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(url, connect_args=connect_args, future=True)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _sqlite_pragmas)
        Base.metadata.create_all(self.engine)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)
        with self._session() as s:
            if s.get(MetaRecord, "schema_version") is None:
                s.add(MetaRecord(key="schema_version", value=str(SCHEMA_VERSION)))

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> ExperimentStore:
        settings = settings or Settings.load()
        return cls(settings.resolved_database_url, home=settings.home)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def dispose(self) -> None:
        self.engine.dispose()

    # -- experiments ---------------------------------------------------------------------------

    def save_experiment(self, experiment: Experiment) -> str:
        record = ExperimentRecord(
            id=experiment.id,
            name=experiment.name,
            created_at=_naive(experiment.created_at),
            dataset_name=experiment.dataset.name,
            dataset=experiment.dataset.model_dump(),
            is_demo=experiment.is_demo,
            tags=list(experiment.tags),
            notes=experiment.notes,
            version=experiment.version,
            metrics=experiment.metrics,
            policy=experiment.policy,
            evaluators=experiment.evaluators,
            summary=experiment.summary.model_dump(mode="json"),
            overall_score=experiment.summary.overall_score,
            num_cases=experiment.summary.num_cases,
        )
        for position, result in enumerate(experiment.results):
            record.cases.append(
                CaseResultRecord(
                    position=position,
                    case_id=result.case_id or f"case-{position:04d}",
                    overall_score=result.overall_score,
                    passed=result.passed,
                    escalations=result.escalations,
                    cost_usd=result.cost_usd,
                    latency_ms=result.latency_ms,
                    has_trace=result.case.trace is not None and bool(result.case.trace.steps),
                    input_preview=(result.case.input or "")[:200],
                    data=result.model_dump(mode="json"),
                )
            )
        with self._session() as s:
            if s.get(ExperimentRecord, experiment.id) is not None:
                raise ValueError(f"experiment {experiment.id} already exists")
            s.add(record)
        return experiment.id

    def resolve(self, ref: str) -> str:
        """Resolve an experiment reference to an id (see module docstring)."""
        ref = ref.strip()
        with self._session() as s:
            if ref.startswith("latest"):
                offset = 0
                if "~" in ref:
                    try:
                        offset = int(ref.split("~", 1)[1])
                    except ValueError:
                        raise NotFoundError(f"invalid reference {ref!r}") from None
                found = s.scalars(
                    select(ExperimentRecord.id).order_by(ExperimentRecord.created_at.desc()).offset(offset).limit(1)
                ).first()
                if found is None:
                    raise NotFoundError("no experiments recorded yet")
                return found
            if s.get(ExperimentRecord, ref) is not None:
                return ref
            by_name = s.scalars(
                select(ExperimentRecord.id)
                .where(ExperimentRecord.name == ref)
                .order_by(ExperimentRecord.created_at.desc())
                .limit(1)
            ).first()
            if by_name is not None:
                return by_name
            prefixed = list(
                s.scalars(select(ExperimentRecord.id).where(ExperimentRecord.id.startswith(ref)).limit(2))
            )
            if len(prefixed) == 1:
                return prefixed[0]
            if len(prefixed) > 1:
                raise NotFoundError(f"experiment reference {ref!r} is ambiguous")
        raise NotFoundError(f"experiment {ref!r} not found")

    def get_experiment(self, ref: str, *, with_results: bool = True) -> Experiment:
        exp_id = self.resolve(ref)
        with self._session() as s:
            record = s.get(ExperimentRecord, exp_id)
            if record is None:  # pragma: no cover - resolve() guarantees existence
                raise NotFoundError(f"experiment {ref!r} not found")
            results = (
                [CaseResult.model_validate(c.data) for c in record.cases] if with_results else []
            )
            return Experiment(
                id=record.id,
                name=record.name,
                created_at=_utc(record.created_at),
                dataset=DatasetRef.model_validate(record.dataset or {}),
                metrics=record.metrics or [],
                policy=record.policy or {},
                evaluators=record.evaluators or {},
                summary=ExperimentSummary.model_validate(record.summary or {}),
                results=results,
                is_demo=record.is_demo,
                tags=record.tags or [],
                notes=record.notes,
                version=record.version,
            )

    def list_experiments(
        self, *, include_demo: bool = True, limit: int = 100, name: str | None = None
    ) -> list[ExperimentListItem]:
        with self._session() as s:
            query = select(ExperimentRecord).order_by(ExperimentRecord.created_at.desc()).limit(limit)
            if not include_demo:
                query = query.where(ExperimentRecord.is_demo.is_(False))
            if name is not None:
                query = query.where(ExperimentRecord.name == name)
            return [
                ExperimentListItem(
                    id=r.id,
                    name=r.name,
                    created_at=_utc(r.created_at),
                    dataset_name=r.dataset_name,
                    is_demo=r.is_demo,
                    tags=r.tags or [],
                    summary=ExperimentSummary.model_validate(r.summary or {}),
                )
                for r in s.scalars(query)
            ]

    def count_experiments(self, *, include_demo: bool = True) -> int:
        with self._session() as s:
            query = select(func.count()).select_from(ExperimentRecord)
            if not include_demo:
                query = query.where(ExperimentRecord.is_demo.is_(False))
            return int(s.scalar(query) or 0)

    def delete_experiment(self, ref: str) -> str:
        exp_id = self.resolve(ref)
        with self._session() as s:
            s.execute(delete(CaseResultRecord).where(CaseResultRecord.experiment_id == exp_id))
            s.execute(delete(ExperimentRecord).where(ExperimentRecord.id == exp_id))
        return exp_id

    def delete_demo_experiments(self) -> int:
        with self._session() as s:
            ids = list(s.scalars(select(ExperimentRecord.id).where(ExperimentRecord.is_demo.is_(True))))
            if ids:
                s.execute(delete(CaseResultRecord).where(CaseResultRecord.experiment_id.in_(ids)))
                s.execute(delete(ExperimentRecord).where(ExperimentRecord.id.in_(ids)))
            return len(ids)

    def case_rows(
        self, ref: str, *, limit: int = 50, offset: int = 0, filter: CaseFilter = "all"
    ) -> tuple[int, list[CaseResultRow]]:
        exp_id = self.resolve(ref)
        with self._session() as s:
            query = select(CaseResultRecord).where(CaseResultRecord.experiment_id == exp_id)
            if filter == "passed":
                query = query.where(CaseResultRecord.passed.is_(True))
            elif filter == "failed":
                query = query.where(CaseResultRecord.passed.is_(False))
            elif filter == "escalated":
                query = query.where(CaseResultRecord.escalations > 0)
            total = int(s.scalar(select(func.count()).select_from(query.subquery())) or 0)
            records = s.scalars(query.order_by(CaseResultRecord.position).offset(offset).limit(limit))
            rows = []
            for r in records:
                metrics = {
                    m["metric"]: MetricCell(score=m.get("score"), passed=m.get("passed"), route=m.get("route", "none"), status=m.get("status", "ok"))
                    for m in r.data.get("metrics", [])
                }
                rows.append(
                    CaseResultRow(
                        case_id=r.case_id,
                        input_preview=r.input_preview,
                        overall_score=r.overall_score,
                        passed=r.passed,
                        latency_ms=r.latency_ms,
                        cost_usd=r.cost_usd,
                        escalations=r.escalations,
                        has_trace=r.has_trace,
                        metrics=metrics,
                    )
                )
            return total, rows

    def get_case(self, ref: str, case_id: str) -> CaseResult:
        exp_id = self.resolve(ref)
        with self._session() as s:
            record = s.scalars(
                select(CaseResultRecord).where(
                    CaseResultRecord.experiment_id == exp_id, CaseResultRecord.case_id == case_id
                )
            ).first()
            if record is None:
                raise NotFoundError(f"case {case_id!r} not found in experiment {exp_id}")
            return CaseResult.model_validate(record.data)

    # -- datasets --------------------------------------------------------------------------------

    def register_dataset(
        self,
        dataset: Dataset,
        *,
        name: str | None = None,
        description: str | None = None,
        copy_to_workspace: bool = True,
        overwrite: bool = False,
    ) -> DatasetInfo:
        """Register a dataset. By default the JSONL is copied into ``<home>/datasets/``."""
        ds_name = name or dataset.name
        path: Path | None = dataset.path
        if copy_to_workspace and self.home is not None:
            target = Path(self.home) / "datasets" / f"{ds_name}.jsonl"
            if target.exists() and not overwrite and (path is None or target.resolve() != Path(path).resolve()):
                raise DatasetError(f"dataset {ds_name!r} already exists in the workspace (use overwrite)")
            target.parent.mkdir(parents=True, exist_ok=True)
            if path is not None and path.suffix.lower() == ".jsonl" and path.resolve() != target.resolve():
                shutil.copyfile(path, target)
            elif path is None or path.resolve() != target.resolve():
                dataset.to_jsonl(target)
            path = target.resolve()
        with self._session() as s:
            record = s.scalars(select(DatasetRecord).where(DatasetRecord.name == ds_name)).first()
            if record is not None and not overwrite:
                raise DatasetError(f"dataset {ds_name!r} is already registered (use overwrite)")
            if record is None:
                record = DatasetRecord(name=ds_name, created_at=_naive(datetime.now(UTC)))
                s.add(record)
            record.path = str(path) if path else None
            record.description = description or dataset.description
            record.num_cases = len(dataset)
            record.hash = dataset.hash
            record.fields = dataset.field_coverage()
            s.flush()
            return _dataset_info(record)

    def list_datasets(self) -> list[DatasetInfo]:
        with self._session() as s:
            return [_dataset_info(r) for r in s.scalars(select(DatasetRecord).order_by(DatasetRecord.name))]

    def get_dataset_info(self, name: str) -> DatasetInfo:
        with self._session() as s:
            record = s.scalars(select(DatasetRecord).where(DatasetRecord.name == name)).first()
            if record is None:
                raise NotFoundError(f"dataset {name!r} is not registered")
            return _dataset_info(record)

    def load_dataset(self, name: str) -> Dataset:
        info = self.get_dataset_info(name)
        if not info.path:
            raise DatasetError(f"dataset {name!r} has no file path")
        return Dataset.from_jsonl(info.path, name=name)

    def delete_dataset(self, name: str) -> None:
        with self._session() as s:
            result = s.execute(delete(DatasetRecord).where(DatasetRecord.name == name))
            if not result.rowcount:  # type: ignore[attr-defined]
                raise NotFoundError(f"dataset {name!r} is not registered")


def _dataset_info(record: DatasetRecord) -> DatasetInfo:
    return DatasetInfo(
        name=record.name,
        path=record.path,
        description=record.description,
        num_cases=record.num_cases,
        hash=record.hash,
        created_at=_utc(record.created_at),
        fields=record.fields or {},
    )


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def resolve_dataset(ref: str | Path, store: ExperimentStore | None = None) -> Dataset:
    """Resolve a dataset reference: a file path, ``sample:<name>``, or a registered name."""
    from evalcascade.datasets import load_sample

    text_ref = str(ref)
    if text_ref.startswith("sample:"):
        return load_sample(text_ref.split(":", 1)[1])
    path = Path(text_ref)
    if path.is_file():
        return Dataset.from_jsonl(path)
    if store is not None:
        try:
            return store.load_dataset(text_ref)
        except NotFoundError:
            pass
    raise DatasetError(
        f"dataset {text_ref!r} not found: not a file, not a registered dataset, "
        "and not sample:<name> (samples: rag_qa, agent_tasks, support_bot)"
    )
