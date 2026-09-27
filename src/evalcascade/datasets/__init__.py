"""Datasets: JSONL collections of evaluation cases."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from evalcascade.datasets.dataset import CASE_FIELDS, Case, Dataset, load_dataset

SAMPLE_DATASETS = ("rag_qa", "agent_tasks", "support_bot")


def sample_path(name: str) -> Path:
    """Path of a sample dataset bundled with the package (``rag_qa``, ``agent_tasks``, ...)."""
    if name not in SAMPLE_DATASETS:
        raise ValueError(
            f"unknown sample dataset {name!r}; available: {', '.join(SAMPLE_DATASETS)}"
        )
    return Path(str(resources.files("evalcascade.datasets") / "data" / f"{name}.jsonl"))


def load_sample(name: str) -> Dataset:
    return Dataset.from_jsonl(sample_path(name), name=name)


__all__ = [
    "CASE_FIELDS",
    "SAMPLE_DATASETS",
    "Case",
    "Dataset",
    "load_dataset",
    "load_sample",
    "sample_path",
]
