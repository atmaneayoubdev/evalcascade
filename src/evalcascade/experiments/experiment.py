"""Experiment records: one run of a metric suite over a dataset."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evalcascade._version import __version__
from evalcascade.core.results import CaseResult
from evalcascade.errors import NotFoundError
from evalcascade.experiments.summary import ExperimentSummary, summarize


def new_experiment_id() -> str:
    return uuid.uuid4().hex[:12]


def utcnow() -> datetime:
    return datetime.now(UTC)


class DatasetRef(BaseModel):
    name: str | None = None
    hash: str | None = None
    size: int = 0
    path: str | None = None


class ExperimentRef(BaseModel):
    id: str
    name: str
    created_at: datetime
    dataset_name: str | None = None
    is_demo: bool = False


class Experiment(BaseModel):
    """A complete, self-contained experiment (exportable to JSON for CI baselines)."""

    id: str = Field(default_factory=new_experiment_id)
    name: str
    created_at: datetime = Field(default_factory=utcnow)
    dataset: DatasetRef = Field(default_factory=DatasetRef)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
    evaluators: dict[str, dict[str, Any]] = Field(default_factory=dict)
    summary: ExperimentSummary = Field(default_factory=ExperimentSummary)
    results: list[CaseResult] = Field(default_factory=list)
    is_demo: bool = False
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    version: str = __version__

    @property
    def dataset_name(self) -> str | None:
        return self.dataset.name

    @property
    def ref(self) -> ExperimentRef:
        return ExperimentRef(
            id=self.id,
            name=self.name,
            created_at=self.created_at,
            dataset_name=self.dataset.name,
            is_demo=self.is_demo,
        )

    def resummarize(self) -> Experiment:
        self.summary = summarize(self.results)
        return self

    def case(self, case_id: str) -> CaseResult:
        for r in self.results:
            if r.case_id == case_id:
                return r
        raise NotFoundError(f"case {case_id!r} not found in experiment {self.id}")

    # -- JSON export (used as CI baselines) ------------------------------------------------

    def to_json(self, path: str | Path | None = None, *, indent: int | None = 2) -> str:
        text = self.model_dump_json(indent=indent)
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text + "\n", encoding="utf-8")
        return text

    @classmethod
    def from_json(cls, path: str | Path) -> Experiment:
        p = Path(path)
        if not p.is_file():
            raise NotFoundError(f"experiment file not found: {p}")
        try:
            return cls.model_validate(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError) as exc:
            raise NotFoundError(f"{p} is not a valid EvalCascade experiment export: {exc}") from exc
