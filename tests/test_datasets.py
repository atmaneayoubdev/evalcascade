"""Dataset loading, validation, persistence and samples."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalcascade.datasets import SAMPLE_DATASETS, Dataset, load_sample, sample_path
from evalcascade.errors import DatasetError


def write(path: Path, rows: list[object] | str) -> Path:
    text = rows if isinstance(rows, str) else "\n".join(json.dumps(r) for r in rows)
    path.write_text(text, encoding="utf-8")
    return path


def test_load_jsonl_with_auto_ids_comments_and_blank_lines(tmp_path: Path) -> None:
    p = write(
        tmp_path / "d.jsonl",
        '{"input": "a", "output": "b"}\n\n// comment\n{"id": "x", "input": "c", "context": "single passage"}\n',
    )
    ds = Dataset.from_jsonl(p)
    assert ds.name == "d" and len(ds) == 2
    assert [c.id for c in ds] == ["case-0001", "x"]
    assert ds.cases[1].context == ["single passage"]
    assert ds.path == p.resolve()


def test_expected_shorthand_and_extra_keys(tmp_path: Path) -> None:
    ds = Dataset.from_jsonl(
        write(
            tmp_path / "d.jsonl",
            [
                {"id": "1", "expected": "Paris"},
                {"id": "2", "expected": {"answer": ["a", "b"], "custom": 5}},
            ],
        )
    )
    assert ds.cases[0].expected is not None and ds.cases[0].expected.answers() == ["Paris"]
    assert ds.cases[1].expected is not None and ds.cases[1].expected.model_extra == {"custom": 5}


def test_invalid_rows_report_line_numbers(tmp_path: Path) -> None:
    p = write(
        tmp_path / "bad.jsonl",
        '{"id": "1"}\n{not json}\n[1,2]\n{"id": "4", "context": 5}\n{"id": "5", "unknown_field": 1}\n',
    )
    with pytest.raises(DatasetError) as info:
        Dataset.from_jsonl(p)
    message = str(info.value)
    assert "4 invalid row(s)" in message
    for fragment in (
        "line 2: invalid JSON",
        "line 3: expected a JSON object",
        "line 4 (id=4)",
        "line 5 (id=5)",
    ):
        assert fragment in message


def test_duplicate_ids_empty_and_missing_files(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="duplicate case ids"):
        Dataset.from_jsonl(write(tmp_path / "dup.jsonl", [{"id": "a"}, {"id": "a"}]))
    with pytest.raises(DatasetError, match="empty"):
        Dataset.from_jsonl(write(tmp_path / "empty.jsonl", "\n\n"))
    with pytest.raises(DatasetError, match="not found"):
        Dataset.from_jsonl(tmp_path / "missing.jsonl")


def test_json_list_and_cases_object(tmp_path: Path) -> None:
    assert (
        len(Dataset.from_jsonl(write(tmp_path / "a.json", json.dumps([{"id": "1"}, {"id": "2"}]))))
        == 2
    )
    assert (
        len(Dataset.from_jsonl(write(tmp_path / "b.json", json.dumps({"cases": [{"id": "1"}]}))))
        == 1
    )
    with pytest.raises(DatasetError, match="expected a JSON list"):
        Dataset.from_jsonl(write(tmp_path / "c.json", json.dumps({"rows": []})))


def test_roundtrip_hash_and_coverage(tmp_path: Path) -> None:
    ds = Dataset.from_records(
        [
            {"input": "q", "output": "a", "context": ["c"]},
            {"input": "q2", "trace": {"steps": [{"type": "message", "content": "hi"}]}},
        ],
        name="mem",
    )
    out = ds.to_jsonl(tmp_path / "out" / "mem.jsonl")
    again = Dataset.from_jsonl(out, name="mem")
    assert again.hash == ds.hash and len(ds.hash) == 16
    assert ds.field_coverage() == {"input": 2, "output": 1, "context": 1, "expected": 0, "trace": 1}
    assert (
        ds.head(1).cases == ds.cases[:1]
        and ds.get("case-0002") is not None
        and ds.get("zzz") is None
    )
    changed = Dataset.from_records([{"input": "q", "output": "different"}], name="mem")
    assert changed.hash != ds.hash


def test_from_records_reports_errors() -> None:
    with pytest.raises(DatasetError, match="record 1"):
        Dataset.from_records([{"context": 3}])


@pytest.mark.parametrize("name", SAMPLE_DATASETS)
def test_bundled_samples_are_valid(name: str) -> None:
    ds = load_sample(name)
    assert len(ds) >= 8 and sample_path(name).is_file()
    assert all(c.input for c in ds)


def test_unknown_sample() -> None:
    with pytest.raises(ValueError, match="unknown sample"):
        sample_path("nope")
