"""Evaluate a RAG answer: groundedness, retrieval quality and citations.

Requires OPENROUTER_API_KEY (and a judge for escalations — see examples/basic.py).

    uv run python examples/rag_eval.py
"""

import asyncio

from evalcascade import EvalSuite
from evalcascade.metrics import (
    AnswerRelevance,
    CitationCorrectness,
    CitationPresence,
    ContextRelevance,
    Groundedness,
)

CONTEXT = [
    "Automated backups run every 6 hours and are retained for 30 days on Business plans "
    "and 7 days on the Starter plan.",
    "Point-in-time restore is available only on Business plans.",
    "The office cafeteria serves coffee from 8am to 4pm on weekdays.",
]


async def main() -> None:
    suite = EvalSuite(
        metrics=[
            AnswerRelevance(),
            Groundedness(),
            ContextRelevance(),
            CitationPresence(),
            CitationCorrectness(),
        ]
    )
    async with suite:
        result = await suite.evaluate(
            input="Can I restore my Starter database to a specific point in time?",
            output="Yes — every plan supports point-in-time restore for 30 days [1]. "
            "Backups run every 6 hours [1].",
            context=CONTEXT,
        )

    print(result.summary())
    passages = result["context_relevance"].details.get("passages", [])
    print("\nper-passage relevance:", [(p["passage"], p["relevance"]) for p in passages])
    citations = result["citation_correctness"].details.get("citations", [])
    for c in citations:
        print(f"  [{c['passage']}] supported={c['supported']:.2f}  {c['claim']}")


if __name__ == "__main__":
    asyncio.run(main())
