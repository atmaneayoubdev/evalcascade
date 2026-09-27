"""Datasets of evaluation cases, stored as JSONL.

One JSON object per line::

    {"id": "case-001", "input": "...", "output": "...", "context": ["..."],
     "expected": {"answer": "..."}, "trace": {"steps": [...], "tools": [...]},
     "metadata": {...}}

Only the fields a metric needs are required by that metric. Rows without an ``id`` get
``case-<line>``; duplicate ids are rejected.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from evalcascade.core.types import EvaluationRequest
from evalcascade.errors import DatasetError

CASE_FIELDS = ("input", "output", "context", "expected", "trace")


class Case(EvaluationRequest):
    """A dataset row: an :class:`EvaluationRequest` with a required ``id``."""

    id: str = Field(min_length=1)


class Dataset(BaseModel):
    """An ordered collection of uniquely identified cases."""

    name: str
    cases: list[Case]
    description: str | None = None
    path: Path | None = None

    # -- construction -----------------------------------------------------------------

    @classmethod
    def from_records(
        cls,
        records: Iterable[dict[str, Any] | EvaluationRequest],
        *,
        name: str = "dataset",
        description: str | None = None,
    ) -> Dataset:
        cases: list[Case] = []
        errors: list[str] = []
        for i, record in enumerate(records, start=1):
            data = record.model_dump() if isinstance(record, EvaluationRequest) else dict(record)
            if not data.get("id"):
                data["id"] = f"case-{i:04d}"
            try:
                cases.append(Case.model_validate(data))
            except ValidationError as exc:
                errors.append(f"record {i}: {_format_validation(exc)}")
        _raise_if(errors, name)
        dataset = cls(name=name, cases=cases, description=description)
        dataset._check_unique_ids()
        return dataset

    @classmethod
    def from_jsonl(cls, path: str | Path, *, name: str | None = None) -> Dataset:
        """Load a ``.jsonl`` file (or a ``.json`` file containing a list of cases)."""
        p = Path(path)
        if not p.is_file():
            raise DatasetError(f"dataset file not found: {p}")
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise DatasetError(f"cannot read {p}: {exc}") from exc

        rows: list[tuple[int, Any]] = []
        errors: list[str] = []
        if p.suffix.lower() == ".json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"{p}: invalid JSON: {exc}") from exc
            items = data.get("cases") if isinstance(data, dict) else data
            if not isinstance(items, list):
                raise DatasetError(f"{p}: expected a JSON list of cases (or {{'cases': [...]}})")
            rows = list(enumerate(items, start=1))
        else:
            for lineno, line in enumerate(text.splitlines(), start=1):
                if not line.strip() or line.lstrip().startswith("//"):
                    continue
                try:
                    rows.append((lineno, json.loads(line)))
                except json.JSONDecodeError as exc:
                    errors.append(f"line {lineno}: invalid JSON ({exc.msg})")

        cases: list[Case] = []
        for lineno, row in rows:
            if not isinstance(row, dict):
                errors.append(f"line {lineno}: expected a JSON object")
                continue
            row = dict(row)
            if not row.get("id"):
                row["id"] = f"case-{lineno:04d}"
            try:
                cases.append(Case.model_validate(row))
            except ValidationError as exc:
                errors.append(f"line {lineno} (id={row.get('id')}): {_format_validation(exc)}")
        dataset_name = name or p.stem
        _raise_if(errors, dataset_name)
        if not cases:
            raise DatasetError(f"{p}: dataset is empty")
        dataset = cls(name=dataset_name, cases=cases, path=p.resolve())
        dataset._check_unique_ids()
        return dataset

    # -- persistence ------------------------------------------------------------------

    def to_jsonl(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="\n") as fh:
            for case in self.cases:
                fh.write(json.dumps(case.model_dump(mode="json", exclude_defaults=True), ensure_ascii=False))
                fh.write("\n")
        return p

    # -- inspection ---------------------------------------------------------------------

    @property
    def hash(self) -> str:
        """Content hash (sha256 of the canonical case JSON), stable across file formatting."""
        digest = hashlib.sha256()
        for case in self.cases:
            digest.update(json.dumps(case.model_dump(mode="json"), sort_keys=True).encode())
            digest.update(b"\n")
        return digest.hexdigest()[:16]

    def field_coverage(self) -> dict[str, int]:
        return {f: sum(1 for c in self.cases if c.has(f)) for f in CASE_FIELDS}

    def head(self, n: int) -> Dataset:
        return self.model_copy(update={"cases": self.cases[:n]})

    def get(self, case_id: str) -> Case | None:
        return next((c for c in self.cases if c.id == case_id), None)

    def __len__(self) -> int:
        return len(self.cases)

    def __iter__(self) -> Iterator[Case]:  # type: ignore[override]
        return iter(self.cases)

    def _check_unique_ids(self) -> None:
        seen: set[str] = set()
        dups: list[str] = []
        for case in self.cases:
            if case.id in seen:
                dups.append(case.id)
            seen.add(case.id)
        if dups:
            raise DatasetError(f"duplicate case ids in {self.name}: {', '.join(sorted(set(dups))[:10])}")


def load_dataset(path: str | Path, *, name: str | None = None) -> Dataset:
    return Dataset.from_jsonl(path, name=name)


def _format_validation(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(x) for x in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def _raise_if(errors: list[str], name: str) -> None:
    if errors:
        shown = "\n  ".join(errors[:20])
        more = f"\n  ... and {len(errors) - 20} more" if len(errors) > 20 else ""
        raise DatasetError(f"dataset {name!r} has {len(errors)} invalid row(s):\n  {shown}{more}")
