"""Run the Jev-only / LLM-judge-only / adaptive-cascade benchmark on a labeled dataset.

    uv run python benchmarks/run_benchmark.py \\
        --dataset benchmarks/data/halueval_groundedness.jsonl --metric groundedness

Requires OPENROUTER_API_KEY (Jev) and a judge configuration (OpenRouter by default, or any
OpenAI-compatible endpoint via EVALCASCADE_JUDGE_BASE_URL / _API_KEY / _MODEL). Results are
written to benchmarks/results/<date>-<name>.json and .md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from evalcascade.benchmarking import MODES, run_benchmark, to_markdown
from evalcascade.config import Settings
from evalcascade.datasets import Dataset

HERE = Path(__file__).resolve().parent


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--metric", default="groundedness")
    parser.add_argument(
        "--param", action="append", default=[], help="metric parameter key=value (JSON value)"
    )
    parser.add_argument("--modes", default=",".join(MODES), help="comma-separated: jev,llm,cascade")
    parser.add_argument("--escalate-below", type=float, default=0.82)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--note", action="append", default=[], help="note added to the report")
    parser.add_argument("--out-dir", type=Path, default=HERE / "results")
    args = parser.parse_args()

    params = {}
    for item in args.param:
        key, raw = item.split("=", 1)
        try:
            params[key] = json.loads(raw)
        except json.JSONDecodeError:
            params[key] = raw
    dataset = Dataset.from_jsonl(args.dataset)
    if args.limit:
        dataset = dataset.head(args.limit)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    def progress(mode: str, done: int, total: int) -> None:
        print(
            f"\r{mode:<8} {done}/{total}",
            end="" if done < total else "\n",
            file=sys.stderr,
            flush=True,
        )

    report = asyncio.run(
        run_benchmark(
            dataset,
            metric=args.metric,
            metric_params=params,
            modes=modes,  # type: ignore[arg-type]
            escalate_below=args.escalate_below,
            concurrency=args.concurrency,
            settings=Settings.load(),
            name=args.name,
            on_progress=progress,
        )
    )
    report.notes.extend(args.note)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    base = args.out_dir / f"{stamp}-{report.name}"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".json").write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown = to_markdown(report)
    base.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\nsaved {base}.json and {base}.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
