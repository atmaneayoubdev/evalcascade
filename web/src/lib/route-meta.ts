import type { EscalationReason, Route, RouteCounts, RoutingSummary } from "./types";

/**
 * The route color system. Every surface that shows where a judgment came from
 * (badges, dots, stacked bars, the cascade, charts) reads from here, so the four
 * routes look identical everywhere in the app.
 */
export interface RouteMeta {
  key: Route;
  label: string;
  short: string;
  description: string;
  /** CSS var for marks (bars, dots, lines). */
  color: string;
  /** CSS var for text on a tinted background. */
  ink: string;
}

export const ROUTE_META: Record<Route, RouteMeta> = {
  deterministic: {
    key: "deterministic",
    label: "Deterministic",
    short: "Det.",
    description: "Resolved by a cheap rule-based check. No model call.",
    color: "var(--route-det)",
    ink: "var(--route-det-ink)",
  },
  jev: {
    key: "jev",
    label: "Jev accepted",
    short: "Jev",
    description: "Jev (System One) answered with confidence at or above the threshold.",
    color: "var(--route-jev)",
    ink: "var(--route-jev-ink)",
  },
  jev_to_llm: {
    key: "jev_to_llm",
    label: "Jev → LLM",
    short: "Esc.",
    description: "Jev was unsure (or failed), so the LLM judge made the final call.",
    color: "var(--route-esc)",
    ink: "var(--route-esc-ink)",
  },
  llm: {
    key: "llm",
    label: "LLM direct",
    short: "LLM",
    description: "Sent straight to the LLM judge, e.g. metrics that require reasoning.",
    color: "var(--route-llm)",
    ink: "var(--route-llm-ink)",
  },
  none: {
    key: "none",
    label: "Not judged",
    short: "None",
    description: "Skipped or errored before any evaluator ran.",
    color: "var(--route-none)",
    ink: "var(--route-none-ink)",
  },
};

/** Cascade order: cheapest first. */
export const ROUTE_ORDER: Route[] = ["deterministic", "jev", "jev_to_llm", "llm", "none"];

export function routeTotal(c: RouteCounts): number {
  return c.deterministic + c.jev + c.jev_to_llm + c.llm + c.none;
}

export const ESCALATION_REASON_LABEL: Record<EscalationReason, string> = {
  low_confidence: "Low confidence",
  primary_error: "Jev call failed",
  requires_reasoning: "Requires reasoning",
};

export const EMPTY_ROUTES: RouteCounts = {
  deterministic: 0,
  jev: 0,
  llm: 0,
  jev_to_llm: 0,
  none: 0,
};

export function addRoutes(a: RouteCounts, b: RouteCounts): RouteCounts {
  return {
    deterministic: a.deterministic + b.deterministic,
    jev: a.jev + b.jev,
    llm: a.llm + b.llm,
    jev_to_llm: a.jev_to_llm + b.jev_to_llm,
    none: a.none + b.none,
  };
}

/** An experiment's RoutingSummary expressed as route counts (skips and errors count as "none"). */
export function routingCounts(r: RoutingSummary): RouteCounts {
  return {
    deterministic: r.deterministic,
    jev: r.jev_accepted,
    jev_to_llm: r.escalated,
    llm: r.llm_direct,
    none: r.skipped + r.errors,
  };
}
