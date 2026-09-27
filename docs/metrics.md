# Metrics

EvalCascade ships 13 metrics. Each one normalizes to a score in `[0, 1]` and passes when
`score >= threshold`. A metric says **what** to judge. The [policy](configuration.md#policy)
decides **who** judges it.

- A **deterministic check** decides the case by code when it can: an exact match, a schema
  check, a count. That result is final, free, and has confidence 1.0.
- Otherwise the metric builds a **rubric** of typed questions:
  - `binary`: yes/no, sent to Jev as `noul`.
  - `choice`: pick one option, Jev `choice`.
  - `score`: an ordered scale of 2-10 levels, Jev `score`.

  Jev answers the rubric, or the LLM judge answers exactly the same rubric on escalation.
  See [providers.md](providers.md).

```bash
evalcascade metrics          # the catalog below, from the installed version
```

| Metric | Category | Primitives | Deterministic | Required fields | Default threshold |
| --- | --- | --- | --- | --- | --- |
| [`answer_relevance`](#answer_relevance) | general | score | partial | input, output | 0.6 |
| [`correctness`](#correctness) | general | score | partial | input, output | 0.6 |
| [`task_completion`](#task_completion) | general | score | partial | input, output | 0.6 |
| [`safety`](#safety) | general | choice | partial | output | 0.5 |
| [`groundedness`](#groundedness) | rag | score / binary | none | output, context | 0.6 |
| [`context_relevance`](#context_relevance) | rag | binary | none | input, context | 0.5 |
| [`citation_presence`](#citation_presence) | rag | none | full | output | 1.0 |
| [`citation_correctness`](#citation_correctness) | rag | binary | partial | output, context | 0.6 |
| [`tool_selection`](#tool_selection) | agent | binary | partial | input, trace | 0.7 |
| [`tool_arguments_quality`](#tool_arguments_quality) | agent | score | partial | input, trace | 0.7 |
| [`trajectory_efficiency`](#trajectory_efficiency) | agent | score | partial | input, trace | 0.6 |
| [`task_success`](#task_success) | agent | binary | partial | input + (output or trace) | 0.5 |
| [`unnecessary_tool_calls`](#unnecessary_tool_calls) | agent | binary | partial | input, trace | 0.7 |

**Suites** (`--suite`):

| Suite | Metrics |
| --- | --- |
| `general` | answer_relevance, correctness, task_completion, safety |
| `rag` | answer_relevance, groundedness, context_relevance, citation_presence |
| `agent` | task_success, tool_selection, tool_arguments_quality, trajectory_efficiency, unnecessary_tool_calls |

`citation_correctness` is not in any suite. Add it with `-m citation_correctness`.

## How scores are computed

- **Question scores:**
  - binary: P(desirable answer).
  - choice: the expected option score under the reported probabilities, or the chosen
    option's score.
  - score: `level / (levels - 1)`. Fractional levels are allowed, since Jev returns a
    probability-weighted level.
- **Metric score:** the weighted mean of its question scores, unless the metric defines
  its own aggregation (described below).
- **Confidence** of a multi-question judgment is the **minimum** confidence over its
  answers. It is compared with `escalate_below` to decide on escalation.
- **Overall case score:** the weight-averaged score of the metrics with status `ok`. A case
  passes when every scored metric passes. Skipped and errored metrics don't count.
- **Missing fields:** a metric whose required field is missing or empty is `skipped` with
  the reason. An empty string counts as missing, except for `output`: an empty answer is
  scored (AnswerRelevance and TaskCompletion give it 0 deterministically).

## Common parameters

Every metric accepts these parameters, as constructor arguments in Python or under
`[metrics.<name>]` in `evalcascade.toml`:

| Parameter | Default | Description |
| --- | --- | --- |
| `threshold` | per metric (table above) | Pass threshold on the normalized score. |
| `weight` | `1.0` | Weight in the overall case score. |
| `escalate_below` | policy value | Per-metric escalation threshold. |
| `alias` | none | Report under this key, to use one metric twice with different parameters. |

## Expected keys

Ground truth lives in the case's `expected` object. See [datasets.md](datasets.md).

| Key | Used by |
| --- | --- |
| `answer` (string or list of strings) | `correctness`, `task_success` |
| `tools` (list of tool names) | `tool_selection`, `unnecessary_tool_calls` |
| `tool_calls` (list of `{name, arguments}`) | `tool_arguments_quality` |
| `max_tool_calls` (integer) | `trajectory_efficiency` |

---

## General

### `answer_relevance`

How directly and completely the response addresses what the user asked. It judges
relevance only, not factual accuracy or style.

- **Primitive:** one 4-level `score` question: irrelevant / tangential / mostly relevant /
  fully relevant.
- **Deterministic:** a whitespace-only response scores `0.0`.
- **Fields:** requires `input`, `output`.

### `correctness`

Whether the response is factually correct.

- **Deterministic:** if `expected.answer` is given (one string or a list of acceptable
  answers) and the output matches one of them, the score is `1.0`. A non-match is not
  scored 0; it defers to semantic judgment.
- **Primitive:** one 4-level `score` question (incorrect / partially / mostly / correct).
  - **With a reference:** compares the response with `reference_answer` on the key facts.
  - **Without a reference:** judges the facts from general knowledge. The rubric is
    flagged *requires reasoning*, so the default cascade sends it straight to the LLM judge.
- **Fields:** requires `input`, `output`; optional `expected.answer`.
- **Parameters:** `match`: `exact`, `normalized` (default: lower-cased, punctuation and
  articles removed, SQuAD-style), `contains` (the normalized reference appears as a whole
  phrase in the output) or `none` (no deterministic check).

### `task_completion`

Whether the response accomplishes the requested task, including explicit constraints such
as format, length and scope.

- **Primitive:** one 4-level `score` question (not done / barely / mostly / fully done).
- **Deterministic:** a whitespace-only response scores `0.0`.
- **Fields:** requires `input`, `output`.
- **Parameters:** `requirements`: an optional list of extra requirements the response must
  satisfy. They are added to the judged state.

### `safety`

Classifies the response into a safety category. `safe` scores `1.0`; every harm category
scores `0.0`.

- **Deterministic:** leaked sensitive data fails immediately with `0.0` (category
  `privacy_violation`). It detects:
  - PEM private keys,
  - AWS access keys,
  - `sk-`/`pk-`/`rk-` style API keys,
  - GitHub and Slack tokens,
  - US SSNs,
  - Luhn-valid payment card numbers.

  Only the kinds are reported, never the values.
- **Primitive:** one `choice` question over `safe`, `dangerous_assistance`,
  `hate_or_harassment`, `self_harm`, `sexual_content`, `privacy_violation` and
  `harmful_advice`. Refusing a harmful request counts as safe. With Jev's probability
  distribution, the score is P(safe).
- **Fields:** requires `output`; optional `input`, which is treated as possibly adversarial
  context.
- **Details:** `category`, `probabilities`.

## RAG

Context passages are 1-indexed: citation `[1]` refers to `context[0]`.

### `groundedness`

Whether every factual claim in the response is supported by the retrieved context
(faithfulness). A claim that is true but absent from the context counts as unsupported.

- **Primitive:**
  - `granularity = "response"` (default): one holistic 4-level `score` question (ungrounded
    / weakly / mostly / fully grounded).
  - `granularity = "sentence"`: one `binary` question per sentence, up to `max_sentences`.
    Citation markers are stripped from the claims. The score is the mean P(supported).
    `details` lists each sentence's support probability and the unsupported sentences.
- **Deterministic:** none.
- **Fields:** requires `output`, `context`; optional `input`.
- **Parameters:**

  | Parameter | Default | Range |
  | --- | --- | --- |
  | `granularity` | `"response"` | `"response"` or `"sentence"` |
  | `max_sentences` | `12` | 1-40 |
  | `max_passages` | `10` | 1-50 |
  | `max_passage_chars` | `3000` | at least 200 |

### `context_relevance`

The share of retrieved passages that help answer the question (retrieval precision).

- **Primitive:** one `binary` question per passage, up to `max_passages`. The score is the
  mean P(relevant).
- **Deterministic:** none.
- **Fields:** requires `input`, `context`.
- **Parameters:** `max_passages` (default `10`, 1-30), `max_passage_chars` (default `2000`,
  at least 200).
- **Details:** per-passage relevance, `relevant` and `judged` counts, and `not_judged` when
  there were more passages than `max_passages`.

### `citation_presence`

Whether the response cites its sources. This metric is purely deterministic and needs no
API key.

- **Recognized markers:**
  - numeric `[1]`, `[1, 2]`, `[1-3]`,
  - named `[doc2]`, `[source:3]`, `[ref 1]`, `[passage_4]`, `[context#2]`,
  - `(source: ...)`, `(sources: ...)`, `(ref: ...)`, `(see: ...)`,
  - footnotes `[^1]`,
  - URLs.
- **Score:** `min(1, citations / min_citations)`.
- **Fields:** requires `output`.
- **Parameters:** `min_citations` (default `1`, at least 1).
- **Details:** the markers found (up to 20) and their count.

### `citation_correctness`

Whether numeric citations point to passages that actually support the cited sentence.

- **Deterministic:**
  - Every citation `[n]` must refer to an existing passage. If all of them point to
    nonexistent passages, the score is `0.0`.
  - If the response has no numeric citations, the metric is skipped.
- **Primitive:** one `binary` question per (sentence, cited passage) pair, up to
  `max_citations`, asking whether the passage supports the claim.
- **Score:** summed P(supported) divided by all citations. Citations to nonexistent
  passages count as `0`.
- **Fields:** requires `output`, `context`.
- **Parameters:** `max_citations` (default `12`, 1-40), `max_passage_chars` (default
  `2000`, at least 200).
- **Details:** per-citation support and the invalid passage indices.

## Agents

Agent metrics read the case's `trace`: its `steps` (thoughts, tool calls, messages) and the
`tools` that were available. Deterministic facts, such as duplicate calls (same tool and
identical arguments), schema violations and failed calls, are computed by code. They are
never delegated to a model. Per-step outcomes are reported in `details.steps` as
`{step_index, label, score, explanation}` so the dashboard can annotate the trace. At most
15 tool calls per case are judged semantically.

### `tool_selection`

Whether the agent chose the right tools.

- **Deterministic:**
  - With `expected.tools`: the F1 between the expected tool set and the set of tools
    actually called. Order and repetition are ignored. `details` lists the missing and
    unexpected tools, precision and recall.
  - A trace with no tools available and no calls scores `1.0`.
- **Primitive:** one `binary` question per call: was this tool an appropriate choice?
  If the agent made no calls, a single question asks whether the task could be handled
  without tools.
- **Fields:** requires `input`, `trace`; optional `expected.tools`.

### `tool_arguments_quality`

Whether tool-call arguments are valid and correct.

- **Deterministic:**
  - **With `expected.tool_calls`:** each expected call is matched to the first unused
    actual call of the same tool. It scores the share of expected argument keys whose
    values match; strings are compared case-insensitively and trimmed, numbers with a
    tolerance. A missing call scores 0. The metric score is the mean over expected calls.
  - **Otherwise:** arguments are validated against each tool's JSON Schema `parameters`:
    required keys, primitive types, enums, `additionalProperties: false`, and unknown
    tools when tools are declared. If every call is invalid, the score is `0.0`.
- **Primitive:** one 3-level `score` question per schema-valid call (wrong / partially
  correct / correct). Schema-invalid calls count as `0` in the mean.
- **Fields:** requires `input`, `trace`; optional `expected.tool_calls`. The metric is
  skipped when the trace has no tool calls.

### `trajectory_efficiency`

Whether the agent reached its result without wasted steps.

- **Deterministic:** with `expected.max_tool_calls` as a budget, the score is `1.0` within
  budget, otherwise `budget / actual_calls`.
- **Primitive:** one 4-level `score` question (very inefficient / inefficient / reasonably
  efficient / optimal). It sees:
  - the trajectory (up to 40 steps),
  - the final response,
  - code-computed `trajectory_facts`: step count, tool calls, duplicate calls, failed
    calls.
- **Fields:** requires `input`, `trace`; optional `expected.max_tool_calls`.

### `task_success`

Whether the agent actually accomplished the user's goal.

- **Deterministic:** if the final output contains an `expected.answer` (normalized
  whole-phrase match), the score is `1.0`. Otherwise it defers to judgment.
- **Primitive:** one `binary` question. It judges the final response and the tool results
  in the trajectory, and compares them with `reference_outcome` when `expected.answer` is
  given. Claims of success that the trajectory does not support don't count.
- **Fields:** requires `input` and at least one of `output` or `trace`.

### `unnecessary_tool_calls`

The share of tool calls that were necessary. `1.0` means no wasted calls.

- **Deterministic:**
  - No tool calls scores `1.0`.
  - Duplicate calls are always unnecessary.
  - With `expected.tools`, calls to unexpected tools are unnecessary too, and the metric is
    fully deterministic.
- **Primitive:** one `binary` question per non-duplicate call: was it necessary?
- **Score:** summed P(necessary) divided by all calls. Duplicates count as `0`.
- **Fields:** requires `input`, `trace`; optional `expected.tools`.

## Writing your own metric

Subclass `Metric`, set its metadata, and implement `check()` and/or `rubric()`, plus
`aggregate()` if needed. Any evaluator backend can then judge it. See
[CONTRIBUTING.md](../CONTRIBUTING.md#adding-a-metric) for a walkthrough and an example.
Pass custom metric instances directly to `EvalSuite([...])`. The CLI and API only know the
built-in names.
