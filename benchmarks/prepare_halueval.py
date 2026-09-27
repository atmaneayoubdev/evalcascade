"""Build a labeled groundedness benchmark from HaluEval (MIT License, RUCAIBox).

HaluEval pairs each question/document with a correct and a hallucinated response. Each pair
becomes two EvalCascade cases with ``expected.label`` = true (right answer, grounded) or false
(hallucinated). Case ids are label-neutral (``...-a`` / ``...-b`` in random order) and only the
fields a groundedness judge needs are sent to evaluators.

    uv run python benchmarks/prepare_halueval.py --qa 50 --summarization 25

Source: https://github.com/RUCAIBox/HaluEval (Li et al., 2023, "HaluEval: A Large-Scale
Hallucination Evaluation Benchmark for Large Language Models").
"""

from __future__ import annotations

import argparse
import json
import random
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/RUCAIBox/HaluEval/main/data"
HERE = Path(__file__).resolve().parent
SUMMARY_PROMPT = "Summarize the document in a few sentences."


def fetch(name: str, cache: Path) -> list[dict[str, str]]:
    path = cache / name
    if not path.exists():
        cache.mkdir(parents=True, exist_ok=True)
        print(f"downloading {BASE}/{name}")
        urllib.request.urlretrieve(f"{BASE}/{name}", path)  # noqa: S310 - fixed https URL
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def pair(
    rng: random.Random, pid: str, base: dict[str, object], right: str, wrong: str, source: str
) -> list[dict[str, object]]:
    variants = [(right, True), (wrong, False)]
    rng.shuffle(variants)
    rows = []
    for suffix, (output, label) in zip("ab", variants, strict=True):
        rows.append(
            {
                "id": f"{pid}-{suffix}",
                **base,
                "output": output,
                "expected": {"label": label},
                "metadata": {"source": source, "pair": pid},
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--qa", type=int, default=50, help="QA pairs to sample")
    parser.add_argument(
        "--summarization", type=int, default=25, help="summarization pairs to sample"
    )
    parser.add_argument(
        "--max-document-chars", type=int, default=6000, help="skip longer documents"
    )
    parser.add_argument("--seed", type=int, default=20260927)
    parser.add_argument("--cache", type=Path, default=HERE / ".cache")
    parser.add_argument("--out", type=Path, default=HERE / "data" / "halueval_groundedness.jsonl")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    rows: list[dict[str, object]] = []

    qa = fetch("qa_data.json", args.cache)
    for n, rec in enumerate(rng.sample(qa, args.qa), start=1):
        base = {"input": rec["question"], "context": [rec["knowledge"]]}
        rows += pair(
            rng, f"qa-{n:03d}", base, rec["right_answer"], rec["hallucinated_answer"], "HaluEval/qa"
        )

    summ = [
        r
        for r in fetch("summarization_data.json", args.cache)
        if len(r["document"]) <= args.max_document_chars
    ]
    for n, rec in enumerate(rng.sample(summ, args.summarization), start=1):
        base = {"input": SUMMARY_PROMPT, "context": [rec["document"]]}
        rows += pair(
            rng,
            f"sum-{n:03d}",
            base,
            rec["right_summary"],
            rec["hallucinated_summary"],
            "HaluEval/summarization",
        )

    rng.shuffle(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    positives = sum(1 for r in rows if r["expected"]["label"])  # type: ignore[index]
    negatives = len(rows) - positives
    print(
        f"wrote {len(rows)} cases ({positives} grounded / {negatives} hallucinated) to {args.out}"
    )


if __name__ == "__main__":
    main()
