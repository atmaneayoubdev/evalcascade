/**
 * EvalCascade local API contract (v0.1).
 *
 * Source of truth for the JSON returned by the FastAPI backend (`evalcascade serve`)
 * and consumed by the dashboard in `web/`. All endpoints live under `/api`.
 * Timestamps are ISO-8601 UTC strings. Scores are normalized to [0, 1].
 * Costs are USD. Latencies are milliseconds.
 */

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

export type QuestionKind = "binary" | "choice" | "score";
export type MetricCategory = "general" | "rag" | "agent";
export type MetricStatus = "ok" | "skipped" | "error";
/** Which path produced the final judgment for a metric. */
export type Route = "deterministic" | "jev" | "llm" | "jev_to_llm" | "none";
export type EscalationReason = "low_confidence" | "primary_error" | "requires_reasoning";
export type EvaluatorKind = "deterministic" | "system_one" | "llm_judge" | "simulated";
export type ConfidenceSource = "provider" | "derived" | "self_reported" | "deterministic";
export type CostSource = "provider" | "estimated" | "unknown" | "none";

export interface Usage {
  input_tokens: number;
  output_tokens: number;
}

// ---------------------------------------------------------------------------
// Cases (dataset rows) and agent traces
// ---------------------------------------------------------------------------

export interface ToolSpec {
  name: string;
  description: string;
  parameters: Record<string, unknown> | null; // JSON Schema
}

export interface ToolCall {
  id: string | null;
  name: string;
  arguments: Record<string, unknown>;
  result: unknown | null;
  error: string | null;
}

export interface TraceStep {
  type: "thought" | "tool_call" | "message";
  content: string | null;
  tool_call: ToolCall | null;
  latency_ms: number | null;
  metadata: Record<string, unknown>;
}

export interface AgentTrace {
  steps: TraceStep[];
  tools: ToolSpec[];
}

export interface Case {
  id: string;
  input: string | null;
  output: string | null;
  context: string[];
  expected: Record<string, unknown> | null;
  trace: AgentTrace | null;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Judgments and results
// ---------------------------------------------------------------------------

export interface Answer {
  question_id: string;
  kind: QuestionKind;
  value: boolean | string | number;
  probability: number | null; // binary only: P(true)
  probabilities: Record<string, number> | null;
  confidence: number | null;
  confidence_source: ConfidenceSource | null;
  score: number; // normalized 0..1
  explanation: string | null;
}

/** One evaluator's verdict on one metric (a metric may have 1 or 2: Jev then LLM). */
export interface Judgment {
  evaluator: string; // "deterministic" | "jev" | "llm" | "openrouter" | "simulated" | custom
  evaluator_kind: EvaluatorKind;
  model: string | null;
  score: number | null;
  confidence: number | null;
  pass_probability: number | null;
  answers: Record<string, Answer>;
  explanation: string | null;
  latency_ms: number;
  usage: Usage;
  cost_usd: number;
  cost_source: CostSource;
  request_id: string | null;
  error: string | null;
  details: Record<string, unknown>;
}

/** Per-step judgment for agent traces (present in MetricResult.details.steps for agent metrics). */
export interface StepJudgment {
  step_index: number; // index into AgentTrace.steps
  label: string; // e.g. "appropriate", "unnecessary", "duplicate", "invalid_arguments"
  score: number | null;
  explanation: string | null;
}

export interface MetricResult {
  metric: string;
  display_name: string;
  category: MetricCategory;
  status: MetricStatus;
  score: number | null;
  passed: boolean | null;
  threshold: number;
  route: Route;
  final_evaluator: string | null;
  escalated: boolean;
  escalation_reason: EscalationReason | null;
  confidence: number | null;
  escalate_below: number | null;
  judgments: Judgment[]; // ordered: primary first, fallback second
  explanation: string | null;
  details: Record<string, unknown> & { steps?: StepJudgment[] };
  latency_ms: number;
  cost_usd: number;
  message: string | null; // reason for skipped / error
}

export interface EvaluationResult {
  case_id: string | null;
  overall_score: number | null;
  passed: boolean | null;
  metrics: MetricResult[];
  latency_ms: number; // wall clock for the whole case
  cost_usd: number;
  escalations: number;
  error: string | null;
}

/** GET /api/experiments/{id}/cases/{case_id} */
export interface CaseResult extends EvaluationResult {
  case: Case;
}

/** Compact row for GET /api/experiments/{id}/cases */
export interface CaseResultRow {
  case_id: string;
  input_preview: string;
  overall_score: number | null;
  passed: boolean | null;
  latency_ms: number;
  cost_usd: number;
  escalations: number;
  has_trace: boolean;
  metrics: Record<string, { score: number | null; passed: boolean | null; route: Route; status: MetricStatus }>;
}

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

// ---------------------------------------------------------------------------
// Experiments
// ---------------------------------------------------------------------------

export interface LatencyStats {
  mean: number | null;
  p50: number | null;
  p95: number | null;
  max: number | null;
}

export interface RouteCounts {
  deterministic: number;
  jev: number; // accepted Jev judgments (no escalation)
  llm: number; // LLM judged directly (no Jev attempt)
  jev_to_llm: number; // Jev escalated to LLM
  none: number; // skipped / errored before any evaluator
}

export interface MetricSummary {
  metric: string;
  display_name: string;
  category: MetricCategory;
  mean: number | null;
  std: number | null;
  min: number | null;
  max: number | null;
  pass_rate: number | null;
  count: number; // status ok
  skipped: number;
  errors: number;
  histogram: number[]; // 10 equal-width bins over [0, 1]
  routes: RouteCounts;
  escalation_rate: number | null; // escalated / Jev attempts for this metric
  mean_latency_ms: number | null;
  cost_usd: number;
}

export interface RoutingSummary {
  total: number; // metric evaluations
  deterministic: number;
  jev_attempts: number;
  jev_accepted: number;
  escalated: number;
  llm_direct: number;
  skipped: number;
  errors: number;
  deterministic_rate: number | null; // deterministic / total
  jev_acceptance_rate: number | null; // jev_accepted / jev_attempts
  escalation_rate: number | null; // escalated / jev_attempts
  llm_rate: number | null; // (escalated + llm_direct) / total
}

export interface ExperimentSummary {
  num_cases: number;
  num_evaluations: number;
  overall_score: number | null;
  pass_rate: number | null;
  metrics: Record<string, MetricSummary>;
  cost_usd: number;
  cost_per_case_usd: number | null;
  cost_complete: boolean; // false if some evaluator calls had unknown cost
  latency_ms: LatencyStats; // per-case wall clock
  routing: RoutingSummary;
  agreement: { compared: number; agreement_rate: number | null }; // Jev vs LLM verdict on escalations
  errors: number;
}

export interface MetricConfig {
  name: string;
  params: Record<string, unknown>; // threshold, weight, escalate_below, ...
}

export interface PolicyConfig {
  deterministic_first: boolean;
  primary: string | null;
  fallback: string | null;
  escalate_below: number;
  escalate_on_error: boolean;
  route_reasoning_to_fallback: boolean;
  overrides: Record<string, Record<string, unknown>>;
}

export interface ExperimentListItem {
  id: string;
  name: string;
  created_at: string;
  dataset_name: string | null;
  is_demo: boolean; // true = synthetic demonstration data, NOT a real evaluation
  tags: string[];
  summary: ExperimentSummary;
}

export interface Experiment extends ExperimentListItem {
  dataset: { name: string | null; hash: string | null; size: number; path: string | null };
  metrics: MetricConfig[];
  policy: PolicyConfig;
  evaluators: Record<string, Record<string, unknown>>; // e.g. { jev: { model, surface }, llm: { model, base_url_host } }
  notes: string | null;
  version: string; // evalcascade version that produced it
}

// ---------------------------------------------------------------------------
// Comparison and gates
// ---------------------------------------------------------------------------

export interface Delta {
  baseline: number | null;
  candidate: number | null;
  delta: number | null; // candidate - baseline
  relative: number | null; // delta / |baseline|
}

export interface CaseDelta {
  case_id: string;
  baseline: number | null;
  candidate: number | null;
  delta: number | null;
}

export interface ExperimentRef {
  id: string;
  name: string;
  created_at: string;
  dataset_name: string | null;
  is_demo: boolean;
}

export interface Comparison {
  baseline: ExperimentRef;
  candidate: ExperimentRef;
  dataset_match: boolean;
  overall_score: Delta;
  pass_rate: Delta;
  cost_usd: Delta;
  cost_per_case_usd: Delta;
  latency_p50_ms: Delta;
  latency_p95_ms: Delta;
  jev_acceptance_rate: Delta;
  escalation_rate: Delta;
  metrics: Record<string, Delta>;
  cases: {
    matched: number;
    improved: number;
    regressed: number;
    unchanged: number;
    only_in_baseline: number;
    only_in_candidate: number;
    top_regressions: CaseDelta[];
    top_improvements: CaseDelta[];
  };
}

export interface GateCheck {
  name: string; // "overall_score" | "metric:<name>" | "cost" | "latency_p95" | "min_score" | ...
  passed: boolean;
  actual: number | null;
  limit: number;
  message: string;
}

/** POST /api/gate  body: GateRequest */
export interface GateRequest {
  baseline: string; // experiment id or name
  candidate: string;
  max_quality_drop?: number; // default 0.03
  metric_thresholds?: Record<string, number>; // per-metric max drop
  max_cost_increase?: number | null; // relative, e.g. 0.2 = +20%
  max_latency_increase?: number | null; // relative, on p95
  min_score?: number | null; // absolute floor on candidate overall score
}

export interface GateResult {
  passed: boolean;
  checks: GateCheck[];
  violations: GateCheck[];
  comparison: Comparison;
}

// ---------------------------------------------------------------------------
// Overview, metrics catalog, datasets, config
// ---------------------------------------------------------------------------

export interface TrendPoint {
  id: string;
  name: string;
  created_at: string;
  overall_score: number | null;
  pass_rate: number | null;
  cost_usd: number;
  escalation_rate: number | null;
  jev_acceptance_rate: number | null;
  is_demo: boolean;
}

export interface RegressionIndicator {
  name: string; // experiment name
  baseline_id: string;
  candidate_id: string;
  delta_overall: number | null;
  regressed: boolean; // delta_overall < -0.03 or any metric drop > 0.05
  is_demo: boolean;
}

/** GET /api/overview?include_demo=true */
export interface Overview {
  has_real_data: boolean;
  has_demo_data: boolean;
  totals: { experiments: number; cases: number; evaluations: number; cost_usd: number };
  averages: {
    overall_score: number | null;
    pass_rate: number | null;
    jev_acceptance_rate: number | null;
    escalation_rate: number | null;
    latency_p50_ms: number | null;
  };
  routing: RouteCounts;
  recent: ExperimentListItem[]; // newest first, up to 10
  trend: TrendPoint[]; // oldest first, up to 30
  regressions: RegressionIndicator[];
}

/** GET /api/metrics */
export interface MetricInfo {
  name: string;
  display_name: string;
  category: MetricCategory;
  description: string;
  primitives: QuestionKind[];
  deterministic: "full" | "partial" | "none";
  required_fields: string[];
  optional_fields: string[];
  default_threshold: number;
  requires_reasoning: boolean;
}

/** GET /api/datasets */
export interface DatasetInfo {
  name: string;
  path: string | null;
  description: string | null;
  num_cases: number;
  hash: string;
  created_at: string;
  fields: Record<"input" | "output" | "context" | "expected" | "trace", number>; // # cases with the field
}

/** GET /api/datasets/{name}?limit&offset */
export interface DatasetDetail {
  dataset: DatasetInfo;
  cases: Page<Case>;
}

/** GET /api/config — never contains secrets */
export interface ConfigSummary {
  version: string;
  database: string; // path or redacted URL
  openrouter_api_key_configured: boolean;
  judge_api_key_configured: boolean;
  api_auth_enabled: boolean;
  jev: { model: string; surface: "decisions" | "systemone"; base_url: string; timeout_s: number; max_retries: number };
  judge: { provider: string; model: string; base_url: string; timeout_s: number; temperature: number };
  policy: PolicyConfig;
}

/** GET /api/health */
export interface Health {
  status: "ok" | "degraded";
  version: string;
  database: "ok" | "error";
}

/**
 * Endpoint index
 *   GET  /api/health                              -> Health
 *   GET  /api/config                              -> ConfigSummary
 *   GET  /api/overview?include_demo=bool          -> Overview
 *   GET  /api/metrics                             -> MetricInfo[]
 *   POST /api/evaluate                            -> EvaluationResult
 *   GET  /api/datasets                            -> DatasetInfo[]
 *   GET  /api/datasets/{name}?limit&offset        -> DatasetDetail
 *   GET  /api/experiments?include_demo&limit      -> ExperimentListItem[]
 *   GET  /api/experiments/{id}                    -> Experiment
 *   GET  /api/experiments/{id}/cases?limit&offset&filter=all|passed|failed|escalated  -> Page<CaseResultRow>
 *   GET  /api/experiments/{id}/cases/{case_id}    -> CaseResult
 *   GET  /api/compare?baseline=&candidate=        -> Comparison
 *   POST /api/gate                                -> GateResult
 * Errors: { detail: string } with 4xx/5xx status.
 */
