# EvalCascade documentation

| Guide | What it covers |
|---|---|
| [CLI reference](cli.md) | every command and option, with examples |
| [Configuration](configuration.md) | `evalcascade.toml`, environment variables, precedence, key routing |
| [Metrics](metrics.md) | the 13 built-in metrics: what they measure, deterministic paths, parameters |
| [Datasets](datasets.md) | the JSONL case format, agent traces, `expected.*` keys, sample datasets |
| [Providers](providers.md) | Jev via the Decisions API, LLM judges, confidence semantics, custom evaluators |
| [Local API](api.md) | FastAPI endpoints, authentication, examples |
| [API contract](api-contract.ts) | TypeScript types of every API response (shared with the dashboard) |
| [Benchmarks](../benchmarks/README.md) | methodology and saved results of the Jev / LLM / cascade comparison |
| [CI gates](../examples/ci/README.md) | exporting baselines and gating pull requests |
| [Security](../SECURITY.md) | how secrets and evaluated data are handled |

New here? Start with the [README](../README.md) quickstart, then run the
[examples](../examples/).
