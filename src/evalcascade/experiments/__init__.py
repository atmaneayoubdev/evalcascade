"""Experiments: recorded runs of a suite over a dataset, their summaries and comparisons."""

from evalcascade.experiments.compare import CaseDelta, Comparison, Delta, compare_experiments
from evalcascade.experiments.experiment import DatasetRef, Experiment, ExperimentRef
from evalcascade.experiments.summary import ExperimentSummary, MetricSummary, summarize

__all__ = [
    "CaseDelta",
    "Comparison",
    "DatasetRef",
    "Delta",
    "Experiment",
    "ExperimentRef",
    "ExperimentSummary",
    "MetricSummary",
    "compare_experiments",
    "summarize",
]
