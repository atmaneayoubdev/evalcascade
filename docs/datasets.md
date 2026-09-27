# Datasets

A dataset is a list of **cases**. Each case is one interaction of the system under test:
a prompt, the system's output, and optionally the retrieved context, ground truth and an
agent trace.

## File format

**JSONL** (recommended) holds one JSON object per line, in UTF-8. Blank lines and lines
starting with `//` are skipped.

```jsonl
{"id": "rag-001", "input": "How long are backups kept?", "output": "Backups are kept for 30 days [1].", "context": ["Automated backups are retained for 30 days."], "expected": {"answer": "30 days"}}
{"id": "sup-002", "input": "What's the capital of Australia?", "output": "Canberra.", "expected": "Canberra"}
```

A **`.json`** file may contain a list of cases or an object `{"cases": [...]}`.

### Case fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | Unique case id. Default: `case-<line number>`, for example `case-0003`. Duplicate ids are rejected. |
| `input` | string | The user input / prompt. |
| `output` | string | The system output being evaluated. |
| `context` | list of strings (or one string) | Retrieved passages, in order. Citation `[1]` refers to the first passage. |
| `expected` | object (or string) | Ground truth; a bare string is shorthand for `{"answer": "..."}`. |
| `trace` | object | Agent trajectory (see below). |
| `metadata` | object | Free-form data, stored with results but not used by metrics. |

Every field except `id` is optional in the file. Each metric declares the fields it needs,
and a case missing a required field is **skipped** for that metric, with the reason. An
empty string or an empty list counts as missing — except `output`: an empty answer is a real
failure, so `"output": ""` is scored (usually 0) rather than skipped. Unknown top-level fields
are rejected, so put extra data in `metadata`.

### `expected`

| Key | Type | Used by |
| --- | --- | --- |
| `answer` | string or list of strings | `correctness` (deterministic match first), `task_success` |
| `tools` | list of tool names | `tool_selection` (F1), `unnecessary_tool_calls` |
| `tool_calls` | list of `{name, arguments}` | `tool_arguments_quality` (argument accuracy) |
| `max_tool_calls` | integer | `trajectory_efficiency` (call budget) |
| `label` | any | Gold label for your own analysis |

Other keys are preserved, so custom metrics can use them.

### `trace`

```json
{
  "tools": [
    {
      "name": "get_weather",
      "description": "Current weather for a city.",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}, "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}},
        "required": ["city"],
        "additionalProperties": false
      }
    }
  ],
  "steps": [
    {"type": "thought", "content": "Use the weather tool."},
    {"type": "tool_call", "tool_call": {"name": "get_weather", "arguments": {"city": "Lisbon", "unit": "celsius"}, "result": {"temp": 22, "conditions": "sunny"}}, "latency_ms": 310},
    {"type": "message", "content": "It's 22°C and sunny in Lisbon."}
  ]
}
```

| Object | Fields |
| --- | --- |
| `tools[]` (tool spec) | `name`, `description` (default `""`), `parameters` (a JSON Schema, used for argument validation) |
| `steps[]` (trace step) | `type`: `thought`, `tool_call` (default) or `message`; `content`; `tool_call`; `latency_ms`; `metadata` |
| `tool_call` | `id`, `name`, `arguments` (object), `result` (any JSON), `error` (string, marks a failed call) |

`arguments` may also be a JSON **string**, as in OpenAI-style traces; it is parsed. Text
that isn't JSON is kept as `{"_raw": "..."}`, and a non-object JSON value as
`{"_value": ...}`. Two calls are duplicates when the tool name and the canonical arguments
are identical.

### Which fields each metric needs

| Metric | Required | Optional |
| --- | --- | --- |
| `answer_relevance`, `task_completion` | input, output | |
| `correctness` | input, output | expected.answer |
| `safety` | output | input |
| `groundedness` | output, context | input |
| `context_relevance` | input, context | |
| `citation_presence` | output | |
| `citation_correctness` | output, context | |
| `tool_selection`, `unnecessary_tool_calls` | input, trace | expected.tools |
| `tool_arguments_quality` | input, trace | expected.tool_calls |
| `trajectory_efficiency` | input, trace | expected.max_tool_calls |
| `task_success` | input, and output or trace | expected.answer |

A trace counts as present only if it has at least one step. See [metrics.md](metrics.md)
for details.

## Validation and identity

Loading validates every row. Errors are reported together with their line numbers (up to
20 are shown):

```text
$ evalcascade datasets validate bad.jsonl
error: dataset 'bad' has 2 invalid row(s):
  line 2: invalid JSON (Expecting ',' delimiter)
  line 3 (id=case-0003): trace.steps.0.type: Input should be 'thought', 'tool_call' or 'message'
```

Each dataset has a **content hash**: the first 16 hex characters of a SHA-256 over the
canonical case JSON. It doesn't change with formatting. `compare` and `gate` use it to tell
whether two experiments ran on the same data (`--require-same-dataset`).

## Sample datasets

Three small datasets ship with the package. They contain deliberately mixed good and bad
outputs.

| Name | Cases | Contents |
| --- | --- | --- |
| `rag_qa` | 12 | RAG answers with context passages and citations; 9 with `expected.answer`. Includes faithful, contradicting, partly fabricated and wrongly cited answers. |
| `agent_tasks` | 8 | Tool-using agent traces with tool schemas; 4 with `expected` (tools, call budgets, answers). Includes ideal, redundant and wrong trajectories. |
| `support_bot` | 10 | Customer-support style Q&A; 4 with `expected.answer`. Includes format-constraint cases, an irrelevant answer, a leaked (test) card number, a safe refusal and a harassing reply. |

Refer to them as `sample:<name>` anywhere a dataset is accepted:

```bash
evalcascade datasets show sample:rag_qa
evalcascade run sample:rag_qa --suite rag --policy deterministic
```

`evalcascade init` also copies them to `./datasets/` and registers them, so you can use
`datasets/rag_qa.jsonl` or just `rag_qa`.

## Dataset references

`run` and `datasets show` resolve a dataset reference in this order:

1. `sample:<name>`, a bundled sample,
2. an existing file path (`.jsonl`, or `.json`),
3. the name of a registered dataset.

## Managing datasets

```bash
evalcascade datasets create my_rag --template rag     # starter file at datasets/my_rag.jsonl, registered
evalcascade datasets validate datasets/my_rag.jsonl   # check a file (exit 1 if invalid)
evalcascade datasets import path/to/cases.jsonl --name support-v2 --description "Q3 tickets"
evalcascade datasets list
evalcascade datasets show support-v2 --limit 10
```

- **`create`** writes a template (`general`, `rag` or `agent`) with example cases to edit,
  and registers the file where it is.
- **`import`** validates the file and copies it into the workspace as
  `<home>/datasets/<name>.jsonl`. JSON lists are converted to JSONL. Use `--force` to
  replace an existing dataset of the same name.

Registered datasets are also available over the API: `GET /api/datasets`,
`GET /api/datasets/{name}`, and `POST /api/datasets` to upload cases as JSON. See
[api.md](api.md).

## Python

```python
from evalcascade import Dataset, EvalSuite, load_dataset
from evalcascade.datasets import load_sample

ds = load_dataset("datasets/rag_qa.jsonl")  # or Dataset.from_jsonl(path, name=...)
ds = Dataset.from_records([{"input": "Hi", "output": "Hello!"}], name="inline")
ds.to_jsonl("datasets/inline.jsonl")
print(len(ds), ds.hash, ds.field_coverage())

sample = load_sample("agent_tasks")
```

A suite can also **generate outputs at run time**. Pass `task=`, a sync or async callable
that receives each case. It returns the output string, or a mapping with any of `output`,
`context`, `trace` and `metadata`:

```python
async def my_app(case):
    answer, passages = await rag_pipeline(case.input)
    return {"output": answer, "context": passages}


experiment = await suite.run("datasets/questions.jsonl", task=my_app, name="candidate")
```
