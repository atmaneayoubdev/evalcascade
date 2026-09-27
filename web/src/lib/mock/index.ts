/**
 * Dev-only mock backend (NEXT_PUBLIC_EVALCASCADE_MOCK=1). Every object it
 * returns is typed against the API contract, and every experiment is flagged
 * `is_demo: true`: these are synthetic numbers, never real evaluations.
 */
import { ApiError, type ApiClient, type CaseFilter } from "../api";
import type { CaseResult, Experiment, ExperimentListItem, MetricConfig, Overview } from "../types";
import { compare, gate, overview, summarize, toRow } from "./aggregate";
import { MOCK_CONFIG, MOCK_HEALTH, MOCK_METRICS, MOCK_POLICY } from "./catalog";
import { AGENT_CASES, RAG_CASES } from "./datasets";
import {
  buildAgentResults,
  buildRagResults,
  metricParams,
  type AgentVariantKey,
  type RagVariant,
} from "./generate";

const RAG_METRICS = ["answer_relevance", "answer_correctness", "groundedness", "context_relevance", "context_recall"];
const AGENT_METRICS = ["tool_selection", "argument_validity", "task_completion", "step_efficiency", "error_recovery"];

const DATASETS = {
  rag_qa: {
    name: "rag_qa",
    hash: "sha256:4be17c09d2a5e8f1",
    size: RAG_CASES.length,
    path: "datasets/rag_qa.jsonl",
  },
  agent_tasks: {
    name: "agent_tasks",
    hash: "sha256:9a03e6b27f41c8d5",
    size: AGENT_CASES.length,
    path: "datasets/agent_tasks.jsonl",
  },
} as const;

type Spec = {
  id: string;
  name: string;
  created_at: string;
  tags: string[];
  notes: string;
} & ({ dataset: "rag_qa"; variant: RagVariant } | { dataset: "agent_tasks"; variant: AgentVariantKey });

const SPECS: Spec[] = [
  {
    id: "exp_3f9a1c07",
    name: "rag-qa-bm25-baseline",
    created_at: "2026-09-08T10:12:44Z",
    dataset: "rag_qa",
    variant: "baseline",
    tags: ["rag", "baseline"],
    notes: "BM25 retrieval, top-3 passages, answer prompt v1.",
  },
  {
    id: "exp_8b21d4e6",
    name: "rag-qa-hybrid-retriever",
    created_at: "2026-09-15T16:40:09Z",
    dataset: "rag_qa",
    variant: "hybrid",
    tags: ["rag", "retrieval"],
    notes: "Hybrid BM25 + embedding retrieval with a reranker. Same answer prompt as the baseline.",
  },
  {
    id: "exp_c47e90b2",
    name: "agent-tools-v1",
    created_at: "2026-09-18T09:05:31Z",
    dataset: "agent_tasks",
    variant: "v1",
    tags: ["agent"],
    notes: "Support agent 1.4: ReAct loop over 13 tools.",
  },
  {
    id: "exp_5d06a8f3",
    name: "rag-qa-prompt-v2",
    created_at: "2026-09-23T13:22:57Z",
    dataset: "rag_qa",
    variant: "v2",
    tags: ["rag", "prompt"],
    notes: "Answer prompt v2 asks for more complete answers. Hybrid retrieval.",
  },
  {
    id: "exp_e19b73da",
    name: "agent-tools-v2-planner",
    created_at: "2026-09-26T11:48:12Z",
    dataset: "agent_tasks",
    variant: "v2",
    tags: ["agent", "planner"],
    notes: "Adds a planning step and a cached fallback for list_incidents.",
  },
];

interface Store {
  experiments: Experiment[];
  cases: Map<string, CaseResult[]>;
}

function build(): Store {
  const experiments: Experiment[] = [];
  const cases = new Map<string, CaseResult[]>();
  for (const spec of SPECS) {
    const names = spec.dataset === "rag_qa" ? RAG_METRICS : AGENT_METRICS;
    const params = metricParams(MOCK_POLICY, names);
    const results =
      spec.dataset === "rag_qa"
        ? buildRagResults(spec.id, spec.variant, MOCK_POLICY, params)
        : buildAgentResults(spec.id, spec.variant, MOCK_POLICY, params);
    cases.set(spec.id, results);
    const metrics: MetricConfig[] = names.map((n) => ({ name: n, params: { ...params[n] } }));
    experiments.push({
      id: spec.id,
      name: spec.name,
      created_at: spec.created_at,
      dataset_name: spec.dataset,
      is_demo: true,
      tags: spec.tags,
      summary: summarize(results, names),
      dataset: { ...DATASETS[spec.dataset] },
      metrics,
      policy: MOCK_POLICY,
      evaluators: {
        deterministic: { checks: "builtin" },
        jev: { model: "typesafe/jev-1.13", surface: "decisions", batch: true },
        llm: { model: "qwen/qwen3.8-27b", base_url_host: "openrouter.ai", temperature: 0, cost: "estimated" },
      },
      notes: spec.notes,
      version: "0.1.0",
    });
  }
  return { experiments, cases };
}

const delay = <T>(v: T, ms = 140) => new Promise<T>((res) => setTimeout(() => res(structuredClone(v)), ms));

function listItem(e: Experiment): ExperimentListItem {
  return {
    id: e.id,
    name: e.name,
    created_at: e.created_at,
    dataset_name: e.dataset_name,
    is_demo: e.is_demo,
    tags: e.tags,
    summary: e.summary,
  };
}

export function createMockClient(variant: "demo" | "empty"): ApiClient {
  const store: Store = variant === "empty" ? { experiments: [], cases: new Map() } : build();

  const find = (idOrName: string, path: string) => {
    const e = store.experiments.find((x) => x.id === idOrName || x.name === idOrName);
    if (!e) throw new ApiError("not_found", path, { status: 404, detail: `Experiment '${idOrName}' not found` });
    return e;
  };
  const cmp = (b: Experiment, c: Experiment) =>
    compare(b, c, store.cases.get(b.id) ?? [], store.cases.get(c.id) ?? []);
  const filterRows = (rows: CaseResult[], filter: CaseFilter) => {
    if (filter === "passed") return rows.filter((r) => r.passed === true);
    if (filter === "failed") return rows.filter((r) => r.passed === false);
    if (filter === "escalated") return rows.filter((r) => r.escalations > 0);
    return rows;
  };

  return {
    health: () => delay(MOCK_HEALTH, 60),
    config: () => delay(MOCK_CONFIG),
    metrics: () => delay(MOCK_METRICS),
    overview: (includeDemo) => {
      const o: Overview = overview(store.experiments, includeDemo, cmp);
      return delay(o);
    },
    experiments: async (opts = {}) => {
      const list = store.experiments
        .filter((e) => (opts.includeDemo ?? true) || !e.is_demo)
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .slice(0, opts.limit ?? 200)
        .map(listItem);
      return delay(list);
    },
    experiment: async (id) => delay(find(id, `/experiments/${id}`)),
    cases: async (id, opts = {}) => {
      const e = find(id, `/experiments/${id}/cases`);
      const rows = filterRows(store.cases.get(e.id) ?? [], opts.filter ?? "all");
      const limit = opts.limit ?? 50;
      const offset = opts.offset ?? 0;
      return delay({ total: rows.length, limit, offset, items: rows.slice(offset, offset + limit).map(toRow) });
    },
    caseResult: async (id, caseId) => {
      const path = `/experiments/${id}/cases/${caseId}`;
      const e = find(id, path);
      const r = store.cases.get(e.id)?.find((x) => x.case_id === caseId);
      if (!r) throw new ApiError("not_found", path, { status: 404, detail: `Case '${caseId}' not found` });
      return delay(r);
    },
    compare: async (b, c) => delay(cmp(find(b, "/compare"), find(c, "/compare"))),
    gate: async (req) => {
      const c = cmp(find(req.baseline, "/gate"), find(req.candidate, "/gate"));
      return delay(gate(req, c), 260);
    },
  };
}
