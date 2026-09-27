/**
 * Builds demo experiment results from the ground truth in `datasets.ts`.
 *
 * It simulates the runtime's cascade so the fixtures look like real output:
 * deterministic checks first, then a Jev judgment with calibrated probabilities,
 * escalating to an LLM judge when Jev's confidence is below `escalate_below`,
 * and metrics that require reasoning going straight to the LLM. Everything is
 * seeded, so the same numbers come back on every load.
 */
import type {
  AgentTrace,
  Answer,
  Case,
  CaseResult,
  EscalationReason,
  Judgment,
  MetricInfo,
  MetricResult,
  PolicyConfig,
  QuestionKind,
  Route,
  StepJudgment,
  TraceStep,
} from "../types";
import { MOCK_METRICS } from "./catalog";
import {
  AGENT_CASES,
  RAG_CASES,
  TOOLS,
  type AgentCase,
  type AgentStep,
  type AgentVariant,
  type RagCase,
  type RagTruth,
} from "./datasets";
import { between, clamp, hexId, intBetween, rngFor, type Rand } from "./rng";

const JEV_MODEL = "typesafe/jev-1.13-20260917";
const LLM_MODEL = "qwen/qwen3.8-27b";
const JEV_PRICE_IN = 0.042 / 1e6;
const LLM_PRICE_IN = 0.42 / 1e6;
const LLM_PRICE_OUT = 3 / 1e6;

const INFO = new Map(MOCK_METRICS.map((m) => [m.name, m]));
function info(name: string): MetricInfo {
  const m = INFO.get(name);
  if (!m) throw new Error(`unknown mock metric ${name}`);
  return m;
}

// ---------------------------------------------------------------------------
// Questions and answers
// ---------------------------------------------------------------------------

interface QSpec {
  id: string;
  kind: QuestionKind;
  /** option labels (choice) or level labels (score), in order */
  options?: string[];
  /** normalized score per option; defaults to i / (n - 1) */
  optionScores?: number[];
  /** boolean for binary; option index for choice/score */
  truth: boolean | number;
  /** 0 = trivial for a fast judge, 1 = coin flip */
  difficulty: number;
}

const LEVELS = ["0", "1", "2", "3", "4"];

function optionScore(q: QSpec, i: number): number {
  const n = q.options?.length ?? 2;
  return q.optionScores?.[i] ?? (n > 1 ? i / (n - 1) : 1);
}

function round(v: number, d = 4) {
  const f = 10 ** d;
  return Math.round(v * f) / f;
}

/** Jev's answer: calibrated probabilities peaked near the truth, flatter when the case is hard. */
function jevAnswer(q: QSpec, r: Rand): Answer {
  if (q.kind === "binary") {
    const pTruth = clamp(0.992 - 0.46 * q.difficulty + between(r, -0.035, 0.035), 0.03, 0.997);
    const p = q.truth ? pTruth : 1 - pTruth;
    const value = p >= 0.5;
    return {
      question_id: q.id,
      kind: "binary",
      value,
      probability: round(p),
      probabilities: null,
      confidence: round(Math.max(p, 1 - p)),
      confidence_source: "derived",
      score: value ? 1 : 0,
      explanation: null,
    };
  }
  const options = q.options ?? LEVELS;
  const n = options.length;
  let peakIdx = q.truth as number;
  // On hard questions Jev sometimes leans to a neighbouring option.
  if (r() < q.difficulty * 0.35) peakIdx = clamp(peakIdx + (r() < 0.5 ? -1 : 1), 0, n - 1);
  const peak = clamp(0.975 - 0.42 * q.difficulty + between(r, -0.04, 0.04), 0.34, 0.985);
  const weights = options.map((_, i) => (i === peakIdx ? 0 : Math.exp(-Math.abs(i - peakIdx) * 1.25) * between(r, 0.7, 1.3)));
  const wSum = weights.reduce((a, b) => a + b, 0) || 1;
  const probs = weights.map((w, i) => (i === peakIdx ? peak : ((1 - peak) * w) / wSum));
  const probabilities: Record<string, number> = {};
  options.forEach((o, i) => (probabilities[o] = round(probs[i])));
  const value = q.kind === "score" ? peakIdx : options[peakIdx];
  return {
    question_id: q.id,
    kind: q.kind,
    value,
    probability: null,
    probabilities,
    confidence: round(peak),
    confidence_source: "provider",
    score: round(optionScore(q, peakIdx)),
    explanation: null,
  };
}

/** The LLM judge's answer: it gets the truth, with a self-reported confidence. */
function llmAnswer(q: QSpec, r: Rand, explanation: string | null = null): Answer {
  const conf = round(between(r, 0.78, 0.96), 2);
  if (q.kind === "binary") {
    const value = Boolean(q.truth);
    return {
      question_id: q.id,
      kind: "binary",
      value,
      probability: null,
      probabilities: null,
      confidence: conf,
      confidence_source: "self_reported",
      score: value ? 1 : 0,
      explanation,
    };
  }
  const options = q.options ?? LEVELS;
  const idx = q.truth as number;
  return {
    question_id: q.id,
    kind: q.kind,
    value: q.kind === "score" ? idx : options[idx],
    probability: null,
    probabilities: null,
    confidence: conf,
    confidence_source: "self_reported",
    score: round(optionScore(q, idx)),
    explanation,
  };
}

function detAnswer(q: QSpec): Answer {
  const value = q.kind === "binary" ? Boolean(q.truth) : q.kind === "score" ? (q.truth as number) : (q.options ?? LEVELS)[q.truth as number];
  const score = q.kind === "binary" ? (q.truth ? 1 : 0) : optionScore(q, q.truth as number);
  return {
    question_id: q.id,
    kind: q.kind,
    value,
    probability: q.kind === "binary" ? (q.truth ? 1 : 0) : null,
    probabilities: null,
    confidence: 1,
    confidence_source: "deterministic",
    score: round(score),
    explanation: null,
  };
}

const meanScore = (answers: Answer[]) =>
  answers.length ? answers.reduce((a, b) => a + b.score, 0) / answers.length : 0;

/** P(metric passes) under Jev's own distributions, by sampling. */
function passProbability(qs: QSpec[], answers: Answer[], threshold: number, r: Rand): number {
  const N = 240;
  let pass = 0;
  for (let s = 0; s < N; s++) {
    let total = 0;
    answers.forEach((a, i) => {
      const q = qs[i];
      if (a.kind === "binary") total += r() < (a.probability ?? 0) ? 1 : 0;
      else {
        const options = q.options ?? LEVELS;
        let u = r();
        let pick = options.length - 1;
        for (let k = 0; k < options.length; k++) {
          u -= a.probabilities?.[options[k]] ?? 0;
          if (u <= 0) {
            pick = k;
            break;
          }
        }
        total += optionScore(q, pick);
      }
    });
    if (total / answers.length >= threshold - 1e-9) pass++;
  }
  return round(pass / N, 3);
}

// ---------------------------------------------------------------------------
// The cascade
// ---------------------------------------------------------------------------

interface MetricPlan {
  metric: string;
  threshold: number;
  escalateBelow: number;
  questions: QSpec[];
  /** characters of text the judges read (drives token counts) */
  textChars: number;
  explain: (answers: Answer[], score: number) => string;
  steps?: (answers: Answer[]) => StepJudgment[];
  /** returns a verdict when a deterministic check can settle the metric */
  deterministic?: () => { questions: QSpec[]; explanation: string; details?: Record<string, unknown> } | null;
  skip?: string;
}

interface Timed {
  result: MetricResult;
  detMs: number;
  jevMs: number;
  llmMs: number;
}

function usageCost(kind: "jev" | "llm", chars: number, nq: number, r: Rand) {
  if (kind === "jev") {
    const input = Math.round(chars / 3.6 + 180 + 40 * nq);
    const output = 6 * nq;
    return { usage: { input_tokens: input, output_tokens: output }, cost: input * JEV_PRICE_IN };
  }
  const input = Math.round(chars / 3.6 + 540 + 32 * nq);
  const output = Math.round(90 + 46 * nq + r() * 70);
  return { usage: { input_tokens: input, output_tokens: output }, cost: input * LLM_PRICE_IN + output * LLM_PRICE_OUT };
}

function runMetric(plan: MetricPlan, policy: PolicyConfig, r: Rand): Timed {
  const mi = info(plan.metric);
  const base = {
    metric: mi.name,
    display_name: mi.display_name,
    category: mi.category,
    threshold: plan.threshold,
  };

  if (plan.skip) {
    return {
      result: {
        ...base,
        status: "skipped",
        score: null,
        passed: null,
        route: "none",
        final_evaluator: null,
        escalated: false,
        escalation_reason: null,
        confidence: null,
        escalate_below: null,
        judgments: [],
        explanation: null,
        details: {},
        latency_ms: 0,
        cost_usd: 0,
        message: plan.skip,
      },
      detMs: 0,
      jevMs: 0,
      llmMs: 0,
    };
  }

  const judgments: Judgment[] = [];
  let route: Route;
  let finalAnswers: Answer[];
  let finalExplanation: string | null = null;
  let escalationReason: EscalationReason | null = null;
  let confidence: number | null = null;
  let escalateBelow: number | null = null;
  let detMs = 0;
  let jevMs = 0;
  let llmMs = 0;
  const extraDetails: Record<string, unknown> = {};

  const det = policy.deterministic_first ? plan.deterministic?.() : null;
  if (det) {
    route = "deterministic";
    finalAnswers = det.questions.map(detAnswer);
    const score = meanScore(finalAnswers);
    detMs = round(between(r, 0.2, 3.5), 2);
    finalExplanation = det.explanation;
    confidence = 1;
    Object.assign(extraDetails, det.details ?? {});
    judgments.push({
      evaluator: "deterministic",
      evaluator_kind: "deterministic",
      model: null,
      score: round(score),
      confidence: 1,
      pass_probability: score >= plan.threshold ? 1 : 0,
      answers: Object.fromEntries(finalAnswers.map((a) => [a.question_id, a])),
      explanation: det.explanation,
      latency_ms: detMs,
      usage: { input_tokens: 0, output_tokens: 0 },
      cost_usd: 0,
      cost_source: "none",
      request_id: null,
      error: null,
      details: { check: mi.name, ...(det.details ?? {}) },
    });
  } else {
    const llmJudge = (): Judgment => {
      const answers = plan.questions.map((q) => llmAnswer(q, r));
      const score = meanScore(answers);
      const explanation = plan.explain(answers, score);
      const { usage, cost } = usageCost("llm", plan.textChars, plan.questions.length, r);
      llmMs = Math.round(between(r, 1350, 3900) + 240 * plan.questions.length);
      return {
        evaluator: "llm",
        evaluator_kind: "llm_judge",
        model: LLM_MODEL,
        score: round(score),
        confidence: round(Math.min(...answers.map((a) => a.confidence ?? 1)), 2),
        pass_probability: null,
        answers: Object.fromEntries(answers.map((a) => [a.question_id, a])),
        explanation,
        latency_ms: llmMs,
        usage,
        cost_usd: round(cost, 7),
        cost_source: "estimated",
        request_id: `gen-${hexId(r, 16)}`,
        error: null,
        details: { temperature: 0, pricing: "OpenRouter list price for qwen/qwen3.8-27b" },
      };
    };

    if (mi.requires_reasoning && policy.route_reasoning_to_fallback) {
      route = "llm";
      escalationReason = null;
      const j = llmJudge();
      judgments.push(j);
      finalAnswers = Object.values(j.answers);
      finalExplanation = j.explanation;
      confidence = j.confidence;
    } else {
      escalateBelow = plan.escalateBelow;
      const primaryFails = r() < 0.022;
      const { usage, cost } = usageCost("jev", plan.textChars, plan.questions.length, r);
      jevMs = Math.round(between(r, 150, 360) + 22 * plan.questions.length);
      if (primaryFails) {
        judgments.push({
          evaluator: "jev",
          evaluator_kind: "system_one",
          model: JEV_MODEL,
          score: null,
          confidence: null,
          pass_probability: null,
          answers: {},
          explanation: null,
          latency_ms: jevMs,
          usage: { input_tokens: 0, output_tokens: 0 },
          cost_usd: 0,
          cost_source: "none",
          request_id: null,
          error: "OpenRouter 529: provider overloaded (after 3 retries)",
          details: { surface: "decisions" },
        });
        escalationReason = "primary_error";
      } else {
        const answers = plan.questions.map((q) => jevAnswer(q, r));
        const score = meanScore(answers);
        confidence = round(Math.min(...answers.map((a) => a.confidence ?? 1)));
        judgments.push({
          evaluator: "jev",
          evaluator_kind: "system_one",
          model: JEV_MODEL,
          score: round(score),
          confidence,
          pass_probability: passProbability(plan.questions, answers, plan.threshold, r),
          answers: Object.fromEntries(answers.map((a) => [a.question_id, a])),
          explanation: null,
          latency_ms: jevMs,
          usage,
          cost_usd: round(cost, 8),
          cost_source: "provider",
          request_id: `dec_${hexId(r, 20)}`,
          error: null,
          details: { surface: "decisions", questions: plan.questions.length },
        });
        if (confidence < plan.escalateBelow) escalationReason = "low_confidence";
      }

      if (escalationReason) {
        route = "jev_to_llm";
        const j = llmJudge();
        judgments.push(j);
        finalAnswers = Object.values(j.answers);
        finalExplanation = j.explanation;
      } else {
        route = "jev";
        finalAnswers = Object.values(judgments[0].answers);
        finalExplanation = null;
      }
    }
  }

  const score = round(meanScore(finalAnswers));
  const steps = plan.steps ? plan.steps(finalAnswers) : undefined;
  const latency = round(judgments.reduce((a, j) => a + j.latency_ms, 0), 2);
  const cost = judgments.reduce((a, j) => a + j.cost_usd, 0);

  return {
    result: {
      ...base,
      status: "ok",
      score,
      passed: score >= plan.threshold - 1e-9,
      route,
      final_evaluator: judgments[judgments.length - 1].evaluator,
      escalated: route === "jev_to_llm",
      escalation_reason: escalationReason,
      confidence,
      escalate_below: escalateBelow,
      judgments,
      explanation: finalExplanation,
      details: { ...extraDetails, ...(steps ? { steps } : {}) },
      latency_ms: latency,
      cost_usd: round(cost, 8),
      message: null,
    },
    detMs,
    jevMs,
    llmMs,
  };
}

// ---------------------------------------------------------------------------
// Experiments
// ---------------------------------------------------------------------------

export type RagVariant = "baseline" | "hybrid" | "v2";
export type AgentVariantKey = "v1" | "v2";

export interface MetricParams {
  threshold: number;
  weight: number;
  escalate_below?: number;
}

export function metricParams(policy: PolicyConfig, names: string[]): Record<string, MetricParams> {
  const out: Record<string, MetricParams> = {};
  for (const n of names) {
    const override = policy.overrides[n] as { escalate_below?: number } | undefined;
    out[n] = {
      threshold: info(n).default_threshold,
      weight: 1,
      ...(override?.escalate_below !== undefined ? { escalate_below: override.escalate_below } : {}),
    };
  }
  return out;
}

const splitSentences = (s: string) => s.split(/(?<=[.!?])\s+/).filter(Boolean);
const normalize = (s: string) =>
  s
    .toLowerCase()
    .replace(/[`"“”'’()[\]{}.,;:!?]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

function ragTruth(c: RagCase, variant: RagVariant): RagTruth {
  const base: RagTruth = {
    ctx: c.ctx,
    rel: c.rel,
    answer: c.answer,
    unsupported: c.unsupported,
    hard: c.hard,
    relevance: c.relevance,
    correct: c.correct,
    recall: c.recall,
  };
  const override = variant === "baseline" ? c.baseline : variant === "v2" ? c.v2 : undefined;
  if (!override) return base;
  const merged = { ...base, ...override };
  if (override.answer !== undefined) {
    merged.unsupported = override.unsupported ?? [];
    merged.hard = override.hard ?? [];
  }
  return merged;
}

const quote = (s: string) => `“${s.length > 90 ? `${s.slice(0, 88)}…` : s}”`;

function levelDifficulty(r: Rand, level: number, hardBoost = 0) {
  return 0.06 + r() * 0.3 + (level > 0 && level < 4 ? 0.11 : 0) + hardBoost;
}

function ragPlans(c: RagCase, t: RagTruth, params: Record<string, MetricParams>, policy: PolicyConfig, r: Rand): MetricPlan[] {
  const esc = (m: string) => params[m]?.escalate_below ?? policy.escalate_below;
  const thr = (m: string) => params[m]?.threshold ?? info(m).default_threshold;
  const ctxChars = t.ctx.join(" ").length;
  const claims = splitSentences(t.answer);
  const unsupported = new Set(t.unsupported ?? []);
  const hard = new Set(t.hard ?? []);
  const plans: MetricPlan[] = [];

  const relevance = t.relevance ?? 4;
  plans.push({
    metric: "answer_relevance",
    threshold: thr("answer_relevance"),
    escalateBelow: esc("answer_relevance"),
    questions: [{ id: "relevance", kind: "score", options: LEVELS, truth: relevance, difficulty: levelDifficulty(r, relevance) }],
    textChars: c.question.length + t.answer.length,
    explain: (a) =>
      [
        "Does not address the question.",
        "Mostly off topic; the question is only touched on.",
        "Partially addresses the question and leaves out what was asked.",
        "Answers the question, with some content the user did not ask for.",
        "Directly answers the question with nothing unrelated.",
      ][Number(a[0].value)] ?? "",
  });

  const correct = t.correct ?? 3;
  const exact = normalize(t.answer).includes(normalize(c.expected));
  plans.push({
    metric: "answer_correctness",
    threshold: thr("answer_correctness"),
    escalateBelow: esc("answer_correctness"),
    questions: [{ id: "correctness", kind: "score", options: LEVELS, truth: correct, difficulty: levelDifficulty(r, correct) }],
    textChars: t.answer.length + c.expected.length + c.question.length,
    deterministic: () =>
      exact
        ? {
            questions: [{ id: "correctness", kind: "score", options: LEVELS, truth: 4, difficulty: 0 }],
            explanation: "The normalized output contains the expected answer verbatim.",
            details: { match: "normalized_contains" },
          }
        : null,
    explain: (a) =>
      [
        "Contradicts the expected answer.",
        "Mostly wrong: the key fact differs from the expected answer.",
        "Partially correct; an important detail differs from the expected answer.",
        "Consistent with the expected answer but omits a detail.",
        "Matches the expected answer.",
      ][Number(a[0].value)] ?? "",
  });

  plans.push({
    metric: "groundedness",
    threshold: thr("groundedness"),
    escalateBelow: esc("groundedness"),
    questions: claims.map((_, i) => ({
      id: `s${i + 1}`,
      kind: "binary",
      truth: !unsupported.has(i),
      difficulty: hard.has(i) ? 0.6 + r() * 0.32 : unsupported.has(i) ? 0.2 + r() * 0.3 : 0.03 + r() * 0.24,
    })),
    textChars: ctxChars + t.answer.length,
    explain: (a) => {
      const bad = a.map((x, i) => (x.value === false ? i : -1)).filter((i) => i >= 0);
      if (bad.length === 0) return `All ${a.length} claims are supported by the retrieved passages.`;
      const which = bad.map((i) => quote(claims[i])).join("; ");
      return `${bad.length} of ${a.length} claims ${bad.length === 1 ? "is" : "are"} not supported by any passage: ${which}.`;
    },
  });

  plans.push({
    metric: "context_relevance",
    threshold: thr("context_relevance"),
    escalateBelow: esc("context_relevance"),
    questions: t.ctx.map((_, i) => ({
      id: `p${i + 1}`,
      kind: "score",
      options: LEVELS,
      truth: t.rel[i] ?? 2,
      difficulty: levelDifficulty(r, t.rel[i] ?? 2, -0.07),
    })),
    textChars: ctxChars + c.question.length,
    explain: (a) => {
      const good = a.map((x, i) => (Number(x.value) >= 3 ? i + 1 : 0)).filter(Boolean);
      const weak = a.map((x, i) => (Number(x.value) <= 1 ? i + 1 : 0)).filter(Boolean);
      const parts: string[] = [];
      if (good.length) parts.push(`Passage${good.length > 1 ? "s" : ""} ${good.join(", ")} directly bear on the question.`);
      if (weak.length) parts.push(`Passage${weak.length > 1 ? "s" : ""} ${weak.join(", ")} ${weak.length > 1 ? "are" : "is"} unrelated.`);
      return parts.join(" ") || "Passages are only loosely related to the question.";
    },
  });

  const recall = t.recall ?? true;
  plans.push({
    metric: "context_recall",
    threshold: thr("context_recall"),
    escalateBelow: esc("context_recall"),
    questions: [{ id: "recall", kind: "binary", truth: recall, difficulty: recall ? 0.04 + r() * 0.26 : 0.3 + r() * 0.3 }],
    textChars: ctxChars + c.expected.length,
    explain: (a) =>
      a[0].value
        ? "The passages contain the facts needed for the expected answer."
        : "None of the passages contain the facts in the expected answer.",
  });

  return plans;
}

const SELECTION_OPTIONS = ["appropriate", "unnecessary", "wrong_tool"];
const EFFICIENCY_OPTIONS = ["necessary", "redundant", "duplicate"];
const RECOVERY_OPTIONS = ["recovered", "retried", "reported", "ignored"];

const SELECTION_TEXT: Record<string, string> = {
  appropriate: "Right tool for this step.",
  unnecessary: "The call adds nothing the agent did not already know.",
  wrong_tool: "This tool cannot accomplish the step.",
};
const EFFICIENCY_TEXT: Record<string, string> = {
  necessary: "Needed to make progress.",
  redundant: "Could have been skipped without changing the outcome.",
  duplicate: "Exact repeat of an earlier call.",
};
const RECOVERY_TEXT: Record<string, string> = {
  recovered: "Recovered from the failure and completed the step another way.",
  retried: "Retried the failed call.",
  reported: "Stopped and reported the failure to the user.",
  ignored: "Continued as if the call had succeeded.",
};

function agentPlans(c: AgentCase, v: AgentVariant, params: Record<string, MetricParams>, policy: PolicyConfig, r: Rand): MetricPlan[] {
  const esc = (m: string) => params[m]?.escalate_below ?? policy.escalate_below;
  const thr = (m: string) => params[m]?.threshold ?? info(m).default_threshold;
  const toolSteps = v.steps.map((s, i) => [s, i] as const).filter(([s]) => s.type === "tool_call");
  const failed = toolSteps.filter(([s]) => s.error);
  const traceChars = JSON.stringify(v.steps).length;
  // Tool-call questions are keyed call_1..call_N (the k-th tool call), as the backend does.
  // step_index in StepJudgment is the 0-based index into the whole trace.
  const callId = (stepIndex: number) => `call_${toolSteps.findIndex(([, i]) => i === stepIndex) + 1}`;
  const stepOf = (id: string) => toolSteps[Number(id.replace("call_", "")) - 1][1];
  const stepById = (id: string): AgentStep => v.steps[stepOf(id)];

  const plans: MetricPlan[] = [];

  plans.push({
    metric: "tool_selection",
    threshold: thr("tool_selection"),
    escalateBelow: esc("tool_selection"),
    questions: toolSteps.map(([s, i]) => {
      const truth = SELECTION_OPTIONS.indexOf(s.sel ?? "appropriate");
      return {
        id: callId(i),
        kind: "choice" as const,
        options: SELECTION_OPTIONS,
        optionScores: [1, 0.35, 0],
        truth,
        difficulty: 0.05 + r() * 0.24 + (truth > 0 ? 0.24 : 0),
      };
    }),
    textChars: c.input.length + traceChars,
    explain: (a) => {
      const off = a.filter((x) => x.value !== "appropriate");
      if (!off.length) return `All ${a.length} tool calls used an appropriate tool.`;
      return off
        .map((x) => `Step ${stepOf(x.question_id) + 1} (${stepById(x.question_id).tool}): ${stepById(x.question_id).note ?? SELECTION_TEXT[String(x.value)]}`)
        .join(" ");
    },
    steps: (a) =>
      a.map((x) => ({
        step_index: stepOf(x.question_id),
        label: String(x.value),
        score: x.score,
        explanation: x.value === "appropriate" ? SELECTION_TEXT.appropriate : (stepById(x.question_id).note ?? SELECTION_TEXT[String(x.value)]),
      })),
  });

  const invalid = toolSteps.filter(([s]) => s.argsValid === false);
  plans.push({
    metric: "argument_validity",
    threshold: thr("argument_validity"),
    escalateBelow: esc("argument_validity"),
    questions: [],
    textChars: traceChars,
    deterministic: () => ({
      questions: toolSteps.map(([s, i]) => ({ id: callId(i), kind: "binary" as const, truth: s.argsValid !== false, difficulty: 0 })),
      explanation: invalid.length
        ? `${invalid.length} of ${toolSteps.length} tool calls failed JSON Schema validation: ${invalid.map(([s, i]) => `${s.tool} at step ${i + 1}`).join(", ")}.`
        : `All ${toolSteps.length} tool calls match their JSON Schemas.`,
      details: { validator: "jsonschema-2020-12" },
    }),
    explain: () => "",
    steps: (a) =>
      a.map((x) => ({
        step_index: stepOf(x.question_id),
        label: x.value ? "valid" : "invalid_arguments",
        score: x.score,
        explanation: x.value ? "Arguments match the tool schema." : (stepById(x.question_id).note ?? "Arguments fail schema validation."),
      })),
  });

  plans.push({
    metric: "task_completion",
    threshold: thr("task_completion"),
    escalateBelow: esc("task_completion"),
    questions: [{ id: "completion", kind: "score", options: LEVELS, truth: v.completion, difficulty: 0.3 }],
    textChars: c.input.length + traceChars + 300,
    explain: () => v.completionNote,
  });

  const duplicates = toolSteps.filter(([s]) => s.duplicate);
  plans.push({
    metric: "step_efficiency",
    threshold: thr("step_efficiency"),
    escalateBelow: esc("step_efficiency"),
    questions: toolSteps.map(([s, i]) => {
      const truth = s.sel && s.sel !== "appropriate" ? 1 : 0;
      return {
        id: callId(i),
        kind: "choice" as const,
        options: EFFICIENCY_OPTIONS,
        optionScores: [1, 0.3, 0],
        truth,
        difficulty: 0.05 + r() * 0.22 + (truth ? 0.2 : 0),
      };
    }),
    textChars: traceChars,
    deterministic: () =>
      duplicates.length
        ? {
            questions: toolSteps.map(([s, i]) => ({
              id: callId(i),
              kind: "choice" as const,
              options: EFFICIENCY_OPTIONS,
              optionScores: [1, 0.3, 0],
              truth: s.duplicate ? 2 : 0,
              difficulty: 0,
            })),
            explanation: `Found ${duplicates.length} exact duplicate tool call${duplicates.length > 1 ? "s" : ""} (same tool, same arguments).`,
            details: { duplicate_steps: duplicates.map(([, i]) => i) },
          }
        : null,
    explain: (a) => {
      const off = a.filter((x) => x.value !== "necessary");
      if (!off.length) return "Every tool call was needed to complete the task.";
      return `${off.length} of ${a.length} tool calls could have been avoided: ${off.map((x) => `step ${stepOf(x.question_id) + 1}`).join(", ")}.`;
    },
    steps: (a) =>
      a.map((x) => ({
        step_index: stepOf(x.question_id),
        label: String(x.value),
        score: x.score,
        explanation: EFFICIENCY_TEXT[String(x.value)] ?? null,
      })),
  });

  plans.push({
    metric: "error_recovery",
    threshold: thr("error_recovery"),
    escalateBelow: esc("error_recovery"),
    skip: failed.length === 0 ? "No failed tool calls in the trace, so there was nothing to recover from." : undefined,
    questions: failed.map(([s, i]) => {
      const truth = RECOVERY_OPTIONS.indexOf(s.rec ?? "reported");
      return {
        id: callId(i),
        kind: "choice" as const,
        options: RECOVERY_OPTIONS,
        optionScores: [1, 0.75, 0.55, 0],
        truth,
        difficulty: 0.12 + r() * 0.28 + (truth === 1 || truth === 2 ? 0.14 : 0),
      };
    }),
    textChars: traceChars,
    explain: (a) =>
      a
        .map((x) => `Step ${stepOf(x.question_id) + 1}: ${stepById(x.question_id).note ?? RECOVERY_TEXT[String(x.value)]}`)
        .join(" "),
    steps: (a) =>
      a.map((x) => ({
        step_index: stepOf(x.question_id),
        label: String(x.value),
        score: x.score,
        explanation: stepById(x.question_id).note ?? RECOVERY_TEXT[String(x.value)] ?? null,
      })),
  });

  return plans;
}

function runCase(
  caseId: string,
  plans: MetricPlan[],
  policy: PolicyConfig,
  seed: string,
  weights: Record<string, MetricParams>,
): Omit<CaseResult, "case"> {
  const metrics: MetricResult[] = [];
  let det = 0;
  let jev = 0;
  let llm = 0;
  for (const plan of plans) {
    const r = rngFor(seed, caseId, plan.metric);
    const t = runMetric(plan, policy, r);
    metrics.push(t.result);
    det += t.detMs;
    jev = Math.max(jev, t.jevMs); // Jev metrics of a case are batched into one call
    llm = Math.max(llm, t.llmMs); // LLM fallbacks run concurrently
  }
  const ok = metrics.filter((m) => m.status === "ok" && m.score !== null);
  const wSum = ok.reduce((a, m) => a + (weights[m.metric]?.weight ?? 1), 0);
  const overall = ok.length ? ok.reduce((a, m) => a + (m.score ?? 0) * (weights[m.metric]?.weight ?? 1), 0) / wSum : null;
  return {
    case_id: caseId,
    overall_score: overall === null ? null : round(overall),
    passed: ok.length ? ok.every((m) => m.passed) : null,
    metrics,
    latency_ms: round(det + jev + llm + 3 + rngFor(seed, caseId, "overhead")() * 6, 1),
    cost_usd: round(metrics.reduce((a, m) => a + m.cost_usd, 0), 8),
    escalations: metrics.filter((m) => m.escalated).length,
    error: null,
  };
}

export function buildRagResults(expId: string, variant: RagVariant, policy: PolicyConfig, params: Record<string, MetricParams>): CaseResult[] {
  return RAG_CASES.map((c, line) => {
    const t = ragTruth(c, variant);
    const r = rngFor(expId, c.id, "plans");
    const plans = ragPlans(c, t, params, policy, r);
    const caseObj: Case = {
      id: c.id,
      input: c.question,
      output: t.answer,
      context: t.ctx,
      expected: { answer: c.expected },
      trace: null,
      metadata: {
        source: "datasets/rag_qa.jsonl",
        line: line + 1,
        retriever: variant === "baseline" ? "bm25" : "hybrid+rerank",
        prompt: variant === "v2" ? "answer-v2" : "answer-v1",
      },
    };
    return { ...runCase(c.id, plans, policy, expId, params), case: caseObj };
  });
}

function buildTrace(c: AgentCase, v: AgentVariant, r: Rand): AgentTrace {
  const steps: TraceStep[] = v.steps.map((s) => ({
    type: s.type,
    content: s.content ?? null,
    tool_call:
      s.type === "tool_call" && s.tool
        ? {
            id: `call_${hexId(r, 10)}`,
            name: s.tool,
            arguments: s.args ?? {},
            result: s.error ? null : (s.result ?? null),
            error: s.error ?? null,
          }
        : null,
    latency_ms: s.ms ?? (s.type === "message" ? intBetween(r, 700, 1600) : intBetween(r, 320, 900)),
    metadata: s.type === "tool_call" ? {} : { model: "gpt-oss-120b" },
  }));
  return { steps, tools: c.tools.map((t) => TOOLS[t]) };
}

export function buildAgentResults(expId: string, variant: AgentVariantKey, policy: PolicyConfig, params: Record<string, MetricParams>): CaseResult[] {
  return AGENT_CASES.map((c, line) => {
    const v: AgentVariant = variant === "v2" && c.v2 ? c.v2 : c;
    const r = rngFor(expId, c.id, "plans");
    const plans = agentPlans(c, v, params, policy, r);
    const last = [...v.steps].reverse().find((s) => s.type === "message");
    const caseObj: Case = {
      id: c.id,
      input: c.input,
      output: last?.content ?? null,
      context: [],
      expected: { tools: c.expected.tools, outcome: c.expected.outcome },
      trace: buildTrace(c, v, rngFor(expId, c.id, "trace")),
      metadata: {
        source: "datasets/agent_tasks.jsonl",
        line: line + 1,
        agent: variant === "v2" ? "support-agent@2.0-planner" : "support-agent@1.4",
      },
    };
    return { ...runCase(c.id, plans, policy, expId, params), case: caseObj };
  });
}
