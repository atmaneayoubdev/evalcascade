"""Scoring functions for benchmark runs: classification quality and calibration.

Calibration is measured on the predicted probability that the case *passes* the metric
(``Judgment.pass_probability``) against the gold label:

* **Brier score** — mean squared error of that probability (lower is better).
* **ECE** — expected calibration error over ``bins`` equal-width probability bins:
  ``sum_b (n_b / N) * |mean_p_b - frac_positive_b|`` (lower is better).
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel


class Classification(BaseModel):
    n: int
    tp: int
    fp: int
    tn: int
    fn: int
    accuracy: float | None
    precision: float | None
    recall: float | None
    f1: float | None
    balanced_accuracy: float | None


class ReliabilityBin(BaseModel):
    lower: float
    upper: float
    count: int
    mean_probability: float | None
    observed_frequency: float | None


class Calibration(BaseModel):
    n: int
    brier: float | None
    ece: float | None
    bins: list[ReliabilityBin]


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def classification(labels: Sequence[bool], predictions: Sequence[bool]) -> Classification:
    """Binary classification metrics with ``True`` (= passes the metric) as the positive class."""
    if len(labels) != len(predictions):
        raise ValueError("labels and predictions must have the same length")
    tp = sum(1 for y, p in zip(labels, predictions, strict=True) if y and p)
    fp = sum(1 for y, p in zip(labels, predictions, strict=True) if not y and p)
    tn = sum(1 for y, p in zip(labels, predictions, strict=True) if not y and not p)
    fn = sum(1 for y, p in zip(labels, predictions, strict=True) if y and not p)
    n = len(labels)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall > 0
        else (0.0 if precision is not None and recall is not None else None)
    )
    tnr = _ratio(tn, tn + fp)
    balanced = (recall + tnr) / 2 if recall is not None and tnr is not None else None
    return Classification(
        n=n,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        accuracy=_ratio(tp + tn, n),
        precision=precision,
        recall=recall,
        f1=f1,
        balanced_accuracy=balanced,
    )


def calibration(
    labels: Sequence[bool], probabilities: Sequence[float], bins: int = 10
) -> Calibration:
    """Brier score, ECE and reliability-diagram data for P(pass)."""
    if len(labels) != len(probabilities):
        raise ValueError("labels and probabilities must have the same length")
    n = len(labels)
    if n == 0:
        return Calibration(n=0, brier=None, ece=None, bins=[])
    ys = [1.0 if y else 0.0 for y in labels]
    ps = [min(1.0, max(0.0, float(p))) for p in probabilities]
    brier = sum((p - y) ** 2 for p, y in zip(ps, ys, strict=True)) / n
    buckets: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for p, y in zip(ps, ys, strict=True):
        buckets[min(bins - 1, int(p * bins))].append((p, y))
    ece = 0.0
    out: list[ReliabilityBin] = []
    for i, bucket in enumerate(buckets):
        lower, upper = i / bins, (i + 1) / bins
        if not bucket:
            out.append(
                ReliabilityBin(
                    lower=lower,
                    upper=upper,
                    count=0,
                    mean_probability=None,
                    observed_frequency=None,
                )
            )
            continue
        mean_p = sum(p for p, _ in bucket) / len(bucket)
        freq = sum(y for _, y in bucket) / len(bucket)
        ece += len(bucket) / n * abs(mean_p - freq)
        out.append(
            ReliabilityBin(
                lower=lower,
                upper=upper,
                count=len(bucket),
                mean_probability=mean_p,
                observed_frequency=freq,
            )
        )
    return Calibration(n=n, brier=brier, ece=ece, bins=out)
