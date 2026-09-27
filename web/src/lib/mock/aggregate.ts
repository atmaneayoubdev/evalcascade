/**
 * Server-side logic the mock client stands in for: experiment summaries,
 * comparisons, regression gates and the overview. Mirrors the semantics
 * documented in docs/api-contract.ts.
 */
import type {
  CaseDelta,
  CaseResult,
  CaseResultRow,
  Comparison,
  Delta,
  Experiment,
  ExperimentRef,
  ExperimentSummary,
  GateCheck,
  GateRequest,
  GateResult,
  LatencyStats,
  MetricResult,
  MetricSummary,
  Overview,
  RegressionIndicator,
  RouteCounts,
  RoutingSummary,
} from "../types";

const EPS = 1e-9;

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
const ratio = (a: number, b: number) => (b > 0 ? a / b : null);

function quantile(xs: number[], q: number): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const pos = (s.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

function std(xs: number[]): number | null {
  const m = mean(xs);
  if (m === null || xs.length < 2) return xs.length === 1 ? 0 : null;
  return Math.sqrt(xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1));
}

export function histogram(scores: number[]): number[] {
  const bins = Array.from({ length: 10 }, () => 0);
  for (const s of scores) bins[Math.min(9, Math.max(0, Math.floor(s * 10)))]++;
  return bins;
}

function emptyRoutes(): RouteCounts {
  return { deterministic: 0, jev: 0, llm: 0, jev_to_llm: 0, none: 0 };
}

function summarizeMetric(results: MetricResult[]): MetricSummary {
  const first = results[0];
  const ok = results.filter((m) => m.status === "ok" && m.score !== null);
  const scores = ok.map((m) => m.score as number);
  const routes = emptyRoutes();
  for (const m of results) routes[m.route]++;
  const jevAttempts = routes.jev + routes.jev_to_llm;
  const passed = ok.filter((m) => m.passed).length;
  return {
    metric: first.metric,
    display_name: first.display_name,
    category: first.category,
    threshold: first.threshold,
    mean: mean(scores),
    std: std(scores),
    min: scores.length ? Math.min(...scores) : null,
    max: scores.length ? Math.max(...scores) : null,
    pass_rate: ratio(passed, ok.length),
    count: ok.length,
    skipped: results.filter((m) => m.status === "skipped").length,
    errors: results.filter((m) => m.status === "error").length,
    histogram: histogram(scores),
    routes,
    escalation_rate: ratio(routes.jev_to_llm, jevAttempts),
    mean_latency_ms: mean(ok.map((m) => m.latency_ms)),
    cost_usd: results.reduce((a, m) => a + m.cost_usd, 0),
  };
}

export function summarize(results: CaseResult[], metricOrder: string[]): ExperimentSummary {
  const all = results.flatMap((r) => r.metrics);
  const byMetric = new Map<string, MetricResult[]>();
  for (const name of metricOrder) byMetric.set(name, []);
  for (const m of all) byMetric.get(m.metric)?.push(m);

  const metrics: Record<string, MetricSummary> = {};
  for (const [name, rs] of byMetric) if (rs.length) metrics[name] = summarizeMetric(rs);

  const count = (pred: (m: MetricResult) => boolean) => all.filter(pred).length;
  const deterministic = count((m) => m.route === "deterministic");
  const jevAccepted = count((m) => m.route === "jev");
  const escalated = count((m) => m.route === "jev_to_llm");
  const llmDirect = count((m) => m.route === "llm");
  const jevAttempts = jevAccepted + escalated;
  const routing: RoutingSummary = {
    total: all.length,
    deterministic,
    jev_attempts: jevAttempts,
    jev_accepted: jevAccepted,
    escalated,
    llm_direct: llmDirect,
    skipped: count((m) => m.status === "skipped"),
    errors: count((m) => m.status === "error"),
    deterministic_rate: ratio(deterministic, all.length),
    jev_acceptance_rate: ratio(jevAccepted, jevAttempts),
    escalation_rate: ratio(escalated, jevAttempts),
    llm_rate: ratio(escalated + llmDirect, all.length),
  };

  // Jev vs LLM verdict agreement on escalations where Jev produced a score.
  let compared = 0;
  let agreed = 0;
  for (const m of all) {
    if (m.route !== "jev_to_llm" || m.judgments.length < 2) continue;
    const [jev, llm] = m.judgments;
    if (jev.score === null || llm.score === null) continue;
    compared++;
    if (jev.score >= m.threshold - EPS === llm.score >= m.threshold - EPS) agreed++;
  }

  const latencies = results.map((r) => r.latency_ms);
  const latency: LatencyStats = {
    mean: mean(latencies),
    p50: quantile(latencies, 0.5),
    p95: quantile(latencies, 0.95),
    max: latencies.length ? Math.max(...latencies) : null,
  };
  const scored = results.filter((r) => r.overall_score !== null);
  const judged = results.filter((r) => r.passed !== null);
  const cost = results.reduce((a, r) => a + r.cost_usd, 0);

  return {
    num_cases: results.length,
    num_evaluations: all.length,
    overall_score: mean(scored.map((r) => r.overall_score as number)),
    pass_rate: ratio(judged.filter((r) => r.passed).length, judged.length),
    metrics,
    cost_usd: cost,
    cost_per_case_usd: ratio(cost, results.length),
    cost_complete: all.every((m) => m.judgments.every((j) => j.cost_source !== "unknown")),
    latency_ms: latency,
    routing,
    agreement: { compared, agreement_rate: ratio(agreed, compared) },
    errors: count((m) => m.status === "error") + results.filter((r) => r.error).length,
  };
}

export function toRow(r: CaseResult): CaseResultRow {
  const input = r.case.input ?? "";
  return {
    case_id: r.case_id ?? r.case.id,
    input_preview: input.length > 140 ? `${input.slice(0, 139)}…` : input,
    overall_score: r.overall_score,
    passed: r.passed,
    latency_ms: r.latency_ms,
    cost_usd: r.cost_usd,
    escalations: r.escalations,
    has_trace: r.case.trace !== null,
    metrics: Object.fromEntries(
      r.metrics.map((m) => [m.metric, { score: m.score, passed: m.passed, route: m.route, status: m.status }]),
    ),
  };
}

// ---------------------------------------------------------------------------
// Comparison and gate
// ---------------------------------------------------------------------------

function delta(baseline: number | null, candidate: number | null): Delta {
  const d = baseline !== null && candidate !== null ? candidate - baseline : null;
  return {
    baseline,
    candidate,
    delta: d,
    relative: d !== null && baseline !== null && Math.abs(baseline) > EPS ? d / Math.abs(baseline) : null,
  };
}

export function ref(e: Experiment): ExperimentRef {
  return { id: e.id, name: e.name, created_at: e.created_at, dataset_name: e.dataset_name, is_demo: e.is_demo };
}

export function compare(
  b: Experiment,
  c: Experiment,
  bCases: CaseResult[],
  cCases: CaseResult[],
): Comparison {
  const bs = b.summary;
  const cs = c.summary;
  const metrics: Record<string, Delta> = {};
  const names = new Set([...Object.keys(bs.metrics), ...Object.keys(cs.metrics)]);
  for (const n of names) metrics[n] = delta(bs.metrics[n]?.mean ?? null, cs.metrics[n]?.mean ?? null);

  const bMap = new Map(bCases.map((r) => [r.case_id ?? r.case.id, r]));
  const cMap = new Map(cCases.map((r) => [r.case_id ?? r.case.id, r]));
  const deltas: CaseDelta[] = [];
  for (const [id, cr] of cMap) {
    const br = bMap.get(id);
    if (!br) continue;
    deltas.push({
      case_id: id,
      baseline: br.overall_score,
      candidate: cr.overall_score,
      delta: br.overall_score !== null && cr.overall_score !== null ? cr.overall_score - br.overall_score : null,
    });
  }
  const withDelta = deltas.filter((d) => d.delta !== null) as (CaseDelta & { delta: number })[];
  const improved = withDelta.filter((d) => d.delta > EPS);
  const regressed = withDelta.filter((d) => d.delta < -EPS);

  return {
    baseline: ref(b),
    candidate: ref(c),
    dataset_match: b.dataset.hash !== null && b.dataset.hash === c.dataset.hash,
    overall_score: delta(bs.overall_score, cs.overall_score),
    pass_rate: delta(bs.pass_rate, cs.pass_rate),
    cost_usd: delta(bs.cost_usd, cs.cost_usd),
    cost_per_case_usd: delta(bs.cost_per_case_usd, cs.cost_per_case_usd),
    latency_p50_ms: delta(bs.latency_ms.p50, cs.latency_ms.p50),
    latency_p95_ms: delta(bs.latency_ms.p95, cs.latency_ms.p95),
    jev_acceptance_rate: delta(bs.routing.jev_acceptance_rate, cs.routing.jev_acceptance_rate),
    escalation_rate: delta(bs.routing.escalation_rate, cs.routing.escalation_rate),
    metrics,
    cases: {
      matched: deltas.length,
      improved: improved.length,
      regressed: regressed.length,
      unchanged: deltas.length - improved.length - regressed.length,
      only_in_baseline: [...bMap.keys()].filter((k) => !cMap.has(k)).length,
      only_in_candidate: [...cMap.keys()].filter((k) => !bMap.has(k)).length,
      top_regressions: [...regressed].sort((x, y) => x.delta - y.delta).slice(0, 5),
      top_improvements: [...improved].sort((x, y) => y.delta - x.delta).slice(0, 5),
    },
  };
}

const f3 = (v: number | null) => (v === null ? "n/a" : v.toFixed(3));
const pct = (v: number | null) => (v === null ? "n/a" : `${(v * 100).toFixed(1)}%`);

/**
 * Mirrors evalcascade.regression.gate: drop checks report `actual` as the drop
 * (baseline - candidate, positive = worse) against `limit`, the allowed drop.
 */
function dropCheck(name: string, d: Delta | undefined, limit: number): GateCheck {
  if (!d || d.baseline === null || d.candidate === null) {
    return { name, passed: false, actual: null, limit, message: "score unavailable in baseline or candidate" };
  }
  const drop = d.baseline - d.candidate;
  return {
    name,
    passed: drop <= limit + EPS,
    actual: drop,
    limit,
    message: `${f3(d.baseline)} -> ${f3(d.candidate)} (drop ${drop >= 0 ? "+" : ""}${drop.toFixed(4)}, max ${limit})`,
  };
}

function relativeCheck(name: string, d: Delta, limit: number): GateCheck {
  if (d.baseline === null || d.candidate === null) return { name, passed: true, actual: null, limit, message: "not measured" };
  const rel = d.baseline === 0 ? (d.candidate === 0 ? 0 : null) : (d.candidate - d.baseline) / Math.abs(d.baseline);
  return {
    name,
    passed: rel !== null && rel <= limit + EPS,
    actual: rel,
    limit,
    message: `${pct(rel)} change (max +${pct(limit)})`,
  };
}

export function gate(req: GateRequest, cmp: Comparison): GateResult {
  const checks: GateCheck[] = [dropCheck("overall_score", cmp.overall_score, req.max_quality_drop ?? 0.03)];

  const limits: Record<string, number> = {};
  if (req.max_metric_drop !== undefined && req.max_metric_drop !== null)
    for (const name of Object.keys(cmp.metrics)) limits[name] = req.max_metric_drop;
  Object.assign(limits, req.metric_thresholds ?? {});
  for (const [name, limit] of Object.entries(limits)) {
    const d = cmp.metrics[name];
    if (d && d.candidate === null && d.baseline !== null)
      checks.push({ name: `metric:${name}`, passed: false, actual: null, limit, message: "metric missing from candidate" });
    else if (d && d.baseline === null && d.candidate !== null)
      checks.push({ name: `metric:${name}`, passed: true, actual: null, limit, message: "new metric (no baseline)" });
    else checks.push(dropCheck(`metric:${name}`, d, limit));
  }

  if (req.max_cost_increase !== undefined && req.max_cost_increase !== null)
    checks.push(relativeCheck("cost", cmp.cost_usd, req.max_cost_increase));
  if (req.max_latency_increase !== undefined && req.max_latency_increase !== null)
    checks.push(relativeCheck("latency_p95", cmp.latency_p95_ms, req.max_latency_increase));
  if (req.min_score !== undefined && req.min_score !== null) {
    const s = cmp.overall_score.candidate;
    checks.push({
      name: "min_score",
      passed: s !== null && s >= req.min_score - EPS,
      actual: s,
      limit: req.min_score,
      message: `candidate overall ${f3(s)} (min ${req.min_score})`,
    });
  }
  if (req.max_escalation_rate !== undefined && req.max_escalation_rate !== null) {
    const rate = cmp.escalation_rate.candidate;
    checks.push({
      name: "escalation_rate",
      passed: rate === null || rate <= req.max_escalation_rate + EPS,
      actual: rate,
      limit: req.max_escalation_rate,
      message: `candidate escalation rate ${pct(rate)} (max ${pct(req.max_escalation_rate)})`,
    });
  }
  if (req.require_same_dataset) {
    checks.push({
      name: "dataset",
      passed: cmp.dataset_match,
      actual: null,
      limit: 1,
      message: cmp.dataset_match ? "same dataset" : "baseline and candidate used different datasets",
    });
  }
  const violations = checks.filter((c) => !c.passed);
  return { passed: violations.length === 0, checks, violations, comparison: cmp };
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

export function overview(
  all: Experiment[],
  includeDemo: boolean,
  compareFn: (b: Experiment, c: Experiment) => Comparison,
): Overview {
  const visible = all.filter((e) => includeDemo || !e.is_demo);
  const newest = [...visible].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const oldest = [...newest].reverse();
  const avg = (pick: (e: Experiment) => number | null) =>
    mean(visible.map(pick).filter((v): v is number => v !== null));

  const routing = emptyRoutes();
  for (const e of visible)
    for (const m of Object.values(e.summary.metrics)) {
      routing.deterministic += m.routes.deterministic;
      routing.jev += m.routes.jev;
      routing.llm += m.routes.llm;
      routing.jev_to_llm += m.routes.jev_to_llm;
      routing.none += m.routes.none;
    }

  // Each experiment against the previous one on the same dataset.
  const regressions: RegressionIndicator[] = [];
  const lastByDataset = new Map<string, Experiment>();
  for (const e of oldest) {
    const key = e.dataset.hash ?? e.dataset_name ?? "";
    const prev = lastByDataset.get(key);
    if (prev) {
      const cmp = compareFn(prev, e);
      const metricDrop = Object.values(cmp.metrics).some((d) => d.delta !== null && d.delta < -0.05);
      const d = cmp.overall_score.delta;
      regressions.push({
        name: e.name,
        baseline_id: prev.id,
        candidate_id: e.id,
        delta_overall: d,
        regressed: (d !== null && d < -0.03) || metricDrop,
        is_demo: e.is_demo || prev.is_demo,
      });
    }
    lastByDataset.set(key, e);
  }
  regressions.reverse();

  return {
    has_real_data: all.some((e) => !e.is_demo),
    has_demo_data: all.some((e) => e.is_demo),
    totals: {
      experiments: visible.length,
      cases: visible.reduce((a, e) => a + e.summary.num_cases, 0),
      evaluations: visible.reduce((a, e) => a + e.summary.num_evaluations, 0),
      cost_usd: visible.reduce((a, e) => a + e.summary.cost_usd, 0),
    },
    averages: {
      overall_score: avg((e) => e.summary.overall_score),
      pass_rate: avg((e) => e.summary.pass_rate),
      jev_acceptance_rate: avg((e) => e.summary.routing.jev_acceptance_rate),
      escalation_rate: avg((e) => e.summary.routing.escalation_rate),
      latency_p50_ms: avg((e) => e.summary.latency_ms.p50),
      latency_mean_ms: avg((e) => e.summary.latency_ms.mean),
    },
    routing,
    recent: newest.slice(0, 10).map((e) => ({
      id: e.id,
      name: e.name,
      created_at: e.created_at,
      dataset_name: e.dataset_name,
      is_demo: e.is_demo,
      tags: e.tags,
      summary: e.summary,
    })),
    trend: oldest.slice(-30).map((e) => ({
      id: e.id,
      name: e.name,
      created_at: e.created_at,
      dataset_name: e.dataset_name,
      overall_score: e.summary.overall_score,
      pass_rate: e.summary.pass_rate,
      cost_usd: e.summary.cost_usd,
      escalation_rate: e.summary.routing.escalation_rate,
      jev_acceptance_rate: e.summary.routing.jev_acceptance_rate,
      is_demo: e.is_demo,
    })),
    regressions,
  };
}
