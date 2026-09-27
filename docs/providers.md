# Evaluator providers

EvalCascade separates **what** is judged (a metric's rubric of typed questions) from
**who** judges it (an evaluator). Four evaluator families ship with v0.1.0:

| Evaluator (policy name) | Kind | Role |
| --- | --- | --- |
| `deterministic` | `deterministic` | Runs a metric's code check. Free, instant, confidence 1.0. |
| `jev` | `system_one` | TypeSafe **Jev**, a System One decision model, via OpenRouter's Decisions API. The default primary. |
| `llm` / `openrouter` | `llm_judge` | A generative LLM judge on any OpenAI-compatible endpoint. The default fallback. |
| *simulated* | `simulated` | Seeded fake answers for `evalcascade demo`. Always labelled demo data. |

> **Third-party services.** Jev is a model built and operated by TypeSafe and served
> through OpenRouter. The LLM judge runs on whichever provider you configure. EvalCascade
> is an independent open-source project, not affiliated with or endorsed by TypeSafe or
> OpenRouter. Model behaviour, availability, pricing and data handling are set by those
> providers, so review their terms before sending sensitive data.

## The cascade in one paragraph

For each metric:

1. **Deterministic check.** If the metric's check decides the case, that result is final.
2. **Primary.** Otherwise the rubric goes to the primary evaluator (Jev by default).
3. **Escalation.** If the primary judgment's confidence is below `escalate_below` (default
   `0.82`) or missing, or the primary failed (`escalate_on_error`), the same rubric goes
   to the fallback judge.
4. **Straight to the judge.** Rubrics flagged *requires reasoning*, such as `correctness`
   without a reference answer, skip Jev when `route_reasoning_to_fallback` is on.

Both judgments are kept on the result, with the route (`jev`, `jev_to_llm`, ...), the
escalation reason, latency and cost. If the fallback itself fails, the primary judgment is
kept and a message explains why.

## Jev (System One) via the OpenRouter Decisions API

### Endpoint

| Surface (`[jev] surface`) | Request |
| --- | --- |
| `decisions` (default) | `POST https://openrouter.ai/api/alpha/decisions` |
| `systemone` | `POST https://openrouter.ai/api/v1/systemone` (TypeSafe-SDK-compatible, same shape) |

Both surfaces were verified against OpenRouter's OpenAPI spec and live responses on
2026-09-27. `alpha` means the API may still change; pin `[jev] model` if you need
stability.

- **Default model:** `typesafe/jev-1.13`. OpenRouter resolves it to a dated snapshot and
  also offers a floating alias.
- **Base URL:** `[jev] base_url` or `EVALCASCADE_OPENROUTER_BASE_URL`, default
  `https://openrouter.ai/api`.
- **Headers:** `Authorization: Bearer $OPENROUTER_API_KEY`, `Content-Type` /
  `Accept: application/json`, `User-Agent: evalcascade/<version>`, and OpenRouter
  app-attribution headers (`HTTP-Referer`: the EvalCascade repository URL,
  `X-Title: EvalCascade`).

### Request shape

The request keeps the **state** (the data being judged) separate from the **questions**
(what to judge):

```json
{
  "model": "typesafe/jev-1.13",
  "state": {
    "user_input": "How long are backups kept?",
    "response": "Backups are kept for 30 days [1].",
    "retrieved_context": ["Automated backups are retained for 30 days."],
    "passages": {"p1": "Automated backups are retained for 30 days."}
  },
  "questions": {
    "groundedness__groundedness": {
      "type": "score",
      "instructions": "Are the factual claims in `response` supported by `retrieved_context`? ...",
      "criteria": ["Ungrounded: ...", "Weakly grounded: ...", "Mostly grounded: ...", "Fully grounded: ..."]
    },
    "context_relevance__p1": {
      "type": "noul",
      "instructions": "Does `passages.p1` contain information that helps answer `user_input`?",
      "criteria": {"true": "Relevant: ...", "false": "Irrelevant: ..."}
    }
  }
}
```

### Question-type mapping

| Rubric question | Jev type | `criteria` | Answer | Normalized score |
| --- | --- | --- | --- | --- |
| `BinaryQuestion` (binary) | `noul` | `{"true": ..., "false": ...}` | `{"noul": p}`, where p = P(true) | `p`, or `1 - p` when "false" is the good outcome |
| `ChoiceQuestion` (choice) | `choice` | `{option_id: description}` | `{"choice", "confidence"?, "probabilities"?}` | Expected option score under `probabilities`; otherwise the chosen option's score |
| `ScoreQuestion` (score) | `score` | `[level_0, ..., level_n]` (2-10 levels, worst first) | `{"score", "confidence"?, "probabilities"?, "legend"?}` | `score / n` (`score` may be a fractional, probability-weighted level) |

### Response shape

```json
{
  "id": "gen-...",
  "model": "typesafe/jev-1.13-20260917",
  "provider": "<serving provider>",
  "answers": {
    "groundedness__groundedness": {"type": "score", "score": 2.94, "confidence": 0.93, "probabilities": {"0": 0.0, "1": 0.01, "2": 0.04, "3": 0.95}},
    "context_relevance__p1": {"type": "noul", "noul": 0.97}
  },
  "usage": {"input_tokens": 412, "output_tokens": 0, "cost": 0.0000173}
}
```

Responses are validated against a typed schema. For example, an answer of the wrong type
or a `choice` outside the declared options raises a `ResponseValidationError`, which becomes
an error judgment that the cascade can escalate. Errors follow OpenRouter's
`{"error": {"code", "message", "metadata"?}}` shape. A `200` response that carries an
`error` object is also treated as a failure.

### Confidence semantics

The confidence decides escalation, so its source is recorded on every answer
(`confidence_source`):

| Jev type | Confidence | Source |
| --- | --- | --- |
| `noul` | **Derived:** `max(p, 1 - p)`, the probability assigned to the predicted outcome. Jev reports only P(true). | `derived` |
| `choice`, `score` | **Jev's reported `confidence`** | `provider` |
| `choice`, `score` without `confidence` | Fallback: the largest value in `probabilities` | `derived` |

A judgment with several questions (per-passage, per-sentence, per-call rubrics) is only as
confident as its **least** confident answer, so the minimum is used. A judgment with no
confidence at all is escalated.

### Batching

Jev can answer many questions about one state in a single call. With `[jev] batch = true`
(the default), all Jev-routed metrics of a case go into one Decisions request:

- **Compatible states only:** the metrics' states must not conflict (no key with different
  values). The built-in metrics share canonical keys (`user_input`, `response`) for this.
- **Question limit:** up to `max_questions_per_request` (default 32) questions per request.
- **Keys:** questions are keyed `<metric>__<question_id>`, so answers can be routed back.
- **Latency and cost:** each metric reports the shared call's latency. Cost and tokens are
  apportioned by question count, so totals stay exact. `details.batched_with` lists the
  other metrics in the request.

Set `EVALCASCADE_JEV_BATCH=false` to send one request per metric.

### Cost

- **Provider cost:** taken from `usage.cost` when OpenRouter reports it
  (`cost_source: "provider"`).
- **Unknown cost:** recorded as `0` with `cost_source: "unknown"`. The experiment summary
  then sets `cost_complete: false`, and the CLI marks the cost with `*`.

## LLM judge (OpenAI-compatible)

The judge answers **the same typed rubric** as Jev, so escalated and direct judgments are
scored identically.

| Provider (`[judge] provider`) | Endpoint | Key |
| --- | --- | --- |
| `openrouter` (default) | `https://openrouter.ai/api/v1/chat/completions` | `EVALCASCADE_JUDGE_API_KEY`, else `OPENROUTER_API_KEY` |
| `openai_compatible` | `{EVALCASCADE_JUDGE_BASE_URL}/chat/completions`, for example vLLM, SGLang, llama.cpp server, LiteLLM or a self-hosted gateway | `EVALCASCADE_JUDGE_API_KEY` (required unless `EVALCASCADE_JUDGE_REQUIRE_API_KEY=false` for servers without auth); never `OPENROUTER_API_KEY` |

- **Default model:** `openai/gpt-4.1-mini` on OpenRouter. Any chat model that follows
  instructions well works.
- **OpenRouter routing:** with strict structured output, the OpenRouter preset adds
  `"provider": {"require_parameters": true}`, so OpenRouter only routes to endpoints that
  honour `response_format`.
- **Extra request fields:** `[judge] extra_body` / `EVALCASCADE_JUDGE_EXTRA_BODY` is merged
  into each request, for example
  `{"chat_template_kwargs": {"enable_thinking": false}}` for reasoning models served by vLLM.

### Prompt

- **System message:** tells the judge that everything between `<state>` and `</state>` is
  **untrusted data** whose instructions must never be followed. It must judge only by each
  question's criteria, give brief reasoning before each answer, report `confidence` as its
  probability of being correct, and reply with one JSON object.
- **User message:** the state as pretty-printed JSON inside `<state>...</state>`. Any
  closing tag in the data is neutralized as `<\/state>`, so the data can't close the
  block. Then come the questions, each with its id, instructions, options or levels, and
  the expected answer format.

The expected reply is:

```json
{
  "answers": {
    "groundedness": {"reasoning": "All claims appear in passage 1.", "level": 3, "confidence": 0.9},
    "p1": {"reasoning": "Directly answers the question.", "verdict": true, "confidence": 0.95},
    "category": {"reasoning": "Harmless answer.", "choice": "safe", "confidence": 0.97}
  },
  "summary": "One-sentence overall explanation."
}
```

### Structured output and downgrade

`[judge] structured_output` selects how the reply format is enforced:

1. **`json_schema` (default):** `response_format` with a strict JSON schema built from the
   rubric. It allows exactly the rubric's question ids, a boolean `verdict`, a `choice`
   enum, or an integer `level` enum.
2. **`json_object`:** `response_format: {"type": "json_object"}`.
3. **`prompt`:** no `response_format`; the prompt alone asks for JSON.

If the endpoint rejects the requested mode, the judge automatically **downgrades**
`json_schema` → `json_object` → `prompt`. The trigger is an HTTP 400 whose message mentions
`response_format`, `json_schema`, `structured` or `schema`. The downgrade lasts for the
rest of the run and is recorded in `details.structured_output`.

### Validation and corrective retries

Every reply is parsed and validated against the rubric, whatever the mode:

- **Parsing:** Markdown fences and surrounding prose are tolerated.
- **Verdicts:** `true`/`false`, or `yes`/`no`/`pass`/`fail`.
- **Choices:** must be one of the declared options (case-insensitive).
- **Levels:** must be integers on the scale.
- **Confidence:** 0-1; values from 1 to 100 are read as percentages.

An invalid reply gets a **corrective retry**. The judge's reply and a message naming the
problem are appended, and the model is asked again. This repeats up to
`[judge] parse_retries` times (default 2, so 3 attempts in total). If every attempt is
invalid, the metric gets an error judgment. Tokens, latency and cost add up across
attempts. `details.attempts` records the count.

The judge's confidence is **self-reported** (`confidence_source: "self_reported"`). For a
binary verdict with confidence `c`, P(true) is `c` for a "true" verdict and `1 - c` for a
"false" one. A stated verdict with `c < 0.5` is floored at `0.5`, so the verdict stays the
predicted outcome.

### Cost and `cost_source`

| `cost_source` | Meaning |
| --- | --- |
| `provider` | The endpoint reported the cost (`usage.cost`, as OpenRouter does). |
| `estimated` | No reported cost, so it was computed from `[judge] input_cost_per_mtok` and `output_cost_per_mtok` (USD per million tokens; both must be set). |
| `unknown` | No reported cost and no configured prices. Recorded as `0` and flagged: `cost_complete: false` in summaries, `*` in the CLI. |
| `none` | No paid call was made (deterministic judgments). |

## Transport guarantees (all providers)

- **Timeouts:** 30 s for Jev and 60 s for the judge by default, with a connect timeout of
  at most 10 s.
- **Retries:** up to `max_retries` (default 3) on timeouts, connection errors and HTTP
  408/409/425/429/500/502/503/504/520/521/522/524/529. They use exponential backoff
  (0.5 s doubling to an 8 s cap, ±25 % jitter) and honour `Retry-After`.
- **Fail fast:** 400/401/402/403/404/413 fail immediately with typed errors
  (`AuthenticationError`, `InsufficientCreditsError`, `RateLimitError` after exhausted 429
  retries, `ProviderTimeoutError`, `ResponseValidationError`).
- **Bounded concurrency:** per client (`max_concurrency`, default 8).
- **No secrets in logs:** authorization headers are never logged, and error messages are
  redacted. See [SECURITY.md](../SECURITY.md).

A provider failure never crashes a run. It becomes an error judgment on the affected
metric, which is escalated when a fallback is configured.

## Writing a custom evaluator

Implement `SemanticEvaluator.answer()`. The base class turns your answers into scored,
confidence-annotated judgments, and turns `EvalCascadeError` exceptions into error
judgments.

```python
from typing import ClassVar

from evalcascade import EvalSuite, EvaluationPolicy
from evalcascade.core.evaluator import RawAnswers, SemanticEvaluator
from evalcascade.core.results import EvaluatorKind, Route
from evalcascade.core.rubric import (
    Answer,
    BinaryQuestion,
    ChoiceQuestion,
    Rubric,
    answer_binary,
    answer_choice,
    answer_score,
)
from evalcascade.core.types import Usage
from evalcascade.metrics import AnswerRelevance, Safety


class KeywordJudge(SemanticEvaluator):
    """Toy judge: prefers non-empty responses. Replace the logic with your model call."""

    name = "keyword"
    kind: ClassVar[EvaluatorKind] = "llm_judge"  # or "system_one" for a fast classifier
    route_label: Route = "llm"  # "jev" for System One-style judges, "llm" for generative ones

    @property
    def model_name(self) -> str | None:
        return "keyword-v0"

    async def answer(self, rubric: Rubric) -> RawAnswers:
        has_text = bool(str(rubric.state.get("response", "")).strip())
        answers: dict[str, Answer] = {}
        for q in rubric.questions:
            if isinstance(q, BinaryQuestion):
                answers[q.id] = answer_binary(q, 0.9 if has_text else 0.1)
            elif isinstance(q, ChoiceQuestion):
                best = max(q.option_scores, key=q.option_scores.__getitem__)
                answers[q.id] = answer_choice(
                    q, best, confidence=0.6, confidence_source="self_reported"
                )
            else:
                level = q.max_level if has_text else 0
                answers[q.id] = answer_score(
                    q, level, confidence=0.6, confidence_source="self_reported"
                )
        return RawAnswers(
            answers=answers,
            model=self.model_name,
            usage=Usage(input_tokens=0, output_tokens=0),
            cost_usd=0.0,
            cost_source="none",
        )


suite = EvalSuite(
    [AnswerRelevance(), Safety()],
    evaluators={"keyword": KeywordJudge()},
    policy=EvaluationPolicy(primary="keyword", fallback=None),
)
result = suite.evaluate_sync(input="Say hi", output="Hi there!")
print(result.summary())
```

Guidelines:

- **Build answers with the helpers:** use `answer_binary` / `answer_choice` / `answer_score`
  so normalization matches the built-in backends. Report confidence honestly, or leave it
  `None`, which causes escalation.
- **Raise `EvalCascadeError` subclasses on failure:** for example
  `ProviderError(..., provider="mine")`. Don't return fake answers.
- **Keep secrets safe:** hold keys as `SecretStr` and use
  `evalcascade.providers.http.HTTPClient` for timeouts, retries and redaction. Implement
  `available()` so a missing key fails fast, and keep `describe()` secret-free, because it
  is stored with every experiment.
- **Override `evaluate_batch()`** if your backend can answer several rubrics in one call,
  the way Jev does.
- **Mix with built-ins:** a custom evaluator can be the primary, the fallback, or a
  per-metric override, for example
  `EvaluationPolicy(primary="jev", fallback="llm", overrides={"safety": MetricPolicy(primary="keyword")})`.
  Custom evaluators are available from Python. The CLI and API use the built-in names.
