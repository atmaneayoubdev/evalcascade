"use client";

import { useState } from "react";
import { ArrowDown, ArrowRight, CircleAlert, CircleSlash } from "lucide-react";
import { AnswerRow, ConfidenceMeter } from "@/components/charts/confidence";
import { RouteBadge } from "@/components/common/route";
import { PassBadge } from "@/components/common/verdict";
import { CATEGORY_LABEL, fmtCost, fmtInt, fmtMs, fmtNum, fmtScore } from "@/lib/format";
import { ESCALATION_REASON_LABEL } from "@/lib/route-meta";
import type { Case, Judgment, MetricResult } from "@/lib/types";
import { questionLabel } from "./question-label";

/** Identity color of the judge (not the route): rules, Jev, or the LLM judge. */
function judgeMeta(j: Judgment): { label: string; color: string } {
  const kind = j.evaluator_kind;
  if (kind === "deterministic") return { label: "Deterministic check", color: "var(--route-det)" };
  if (kind === "system_one") return { label: "Jev (System One)", color: "var(--route-jev)" };
  if (kind === "llm_judge") return { label: "LLM judge", color: "var(--route-llm)" };
  // simulated / custom evaluators: infer from the name
  const n = j.evaluator.toLowerCase();
  if (n.includes("jev") || n.includes("system")) return { label: `${j.evaluator} (simulated)`, color: "var(--route-jev)" };
  if (n.includes("determin")) return { label: j.evaluator, color: "var(--route-det)" };
  return { label: kind === "simulated" ? `${j.evaluator} (simulated)` : j.evaluator, color: "var(--route-llm)" };
}

const COST_SOURCE_NOTE: Record<Judgment["cost_source"], string | null> = {
  provider: null,
  estimated: "estimated",
  unknown: "unknown",
  none: null,
};

function JudgmentBlock({
  j,
  metric,
  showThreshold,
  caseData,
}: {
  j: Judgment;
  metric: MetricResult;
  showThreshold: boolean;
  caseData?: Case | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const meta = judgeMeta(j);
  const answers = Object.values(j.answers);
  const shown = expanded ? answers : answers.slice(0, 5);
  const isJev = j.evaluator_kind === "system_one" || (j.evaluator_kind === "simulated" && meta.color === "var(--route-jev)");
  const costNote = COST_SOURCE_NOTE[j.cost_source];

  return (
    <div className="min-w-0 overflow-hidden rounded-lg border border-hairline bg-surface">
      <div className="h-[3px]" style={{ background: meta.color }} aria-hidden />
      <div className="px-3.5 pt-2.5 pb-3">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <span className="text-[0.8125rem] font-semibold text-ink">{meta.label}</span>
          {j.model && <span className="truncate font-mono text-2xs text-ink-3">{j.model}</span>}
        </div>

        {j.error ? (
          <div className="mt-2 flex items-start gap-2 rounded-md px-2.5 py-2 text-xs text-bad-ink" style={{ background: "color-mix(in oklab, var(--bad) 9%, var(--surface))" }}>
            <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden />
            <span className="break-words">{j.error}</span>
          </div>
        ) : (
          <>
            <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs text-ink-3">
              <span>
                Score <span className="tabular text-sm font-semibold text-ink">{fmtScore(j.score)}</span>
              </span>
              {j.pass_probability !== null && (
                <span>
                  P(pass) <span className="tabular font-medium text-ink">{fmtNum(j.pass_probability, 2)}</span>
                </span>
              )}
              {!isJev && j.confidence !== null && (
                <span>
                  Confidence <span className="tabular font-medium text-ink">{fmtNum(j.confidence, 2)}</span>
                  {j.evaluator_kind === "llm_judge" && " (self-reported)"}
                </span>
              )}
            </div>
            {isJev && (
              <ConfidenceMeter
                className="mt-2.5"
                value={j.confidence}
                threshold={showThreshold ? metric.escalate_below : null}
              />
            )}
            {j.explanation && <p className="mt-2.5 text-[0.8125rem] leading-relaxed text-ink">{j.explanation}</p>}
            {isJev && !j.explanation && (
              <p className="mt-2 text-2xs text-ink-3">Jev returns calibrated probabilities, not a written rationale.</p>
            )}
            {answers.length > 0 && (
              <div className="mt-2.5 divide-y divide-hairline border-t border-hairline">
                {shown.map((a) => (
                  <AnswerRow key={a.question_id} answer={a} accent={meta.color} label={questionLabel(a.question_id, caseData)} />
                ))}
              </div>
            )}
            {answers.length > 5 && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="mt-1 rounded-sm text-xs font-medium text-ink-2 hover:text-ink"
              >
                {expanded ? "Show fewer" : `Show all ${answers.length} answers`}
              </button>
            )}
          </>
        )}

        <div className="tabular mt-2.5 flex flex-wrap gap-x-4 gap-y-0.5 border-t border-hairline pt-2 text-2xs text-ink-3">
          <span>
            <span className="text-ink-2">{fmtMs(j.latency_ms)}</span> latency
          </span>
          <span>
            <span className="text-ink-2">{fmtCost(j.cost_usd)}</span>
            {costNote && ` (${costNote})`}
          </span>
          {(j.usage.input_tokens > 0 || j.usage.output_tokens > 0) && (
            <span>
              {fmtInt(j.usage.input_tokens)} in / {fmtInt(j.usage.output_tokens)} out tokens
            </span>
          )}
          {j.request_id && (
            <span className="max-w-[14rem] truncate font-mono" title={j.request_id}>
              {j.request_id}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

type ConnectorTone = "esc" | "jev" | "det" | "llm";

function Connector({ tone, title, lines, label }: { tone: ConnectorTone; title: string; lines: (string | null)[]; label: string }) {
  const color = `var(--route-${tone})`;
  const ink = `var(--route-${tone}-ink)`;
  return (
    <div className="flex items-center justify-center gap-2 py-1 lg:mt-9 lg:flex-col lg:gap-1.5 lg:self-start lg:py-0" aria-label={label}>
      <ArrowDown className="size-4 lg:hidden" style={{ color: ink }} aria-hidden />
      <ArrowRight className="hidden size-4 lg:block" style={{ color: ink }} aria-hidden />
      <span
        className="rounded-md px-2 py-1 text-center text-2xs leading-tight font-medium"
        style={{ color: ink, background: `color-mix(in oklab, ${color} 13%, var(--surface))` }}
      >
        {title}
        {lines.filter(Boolean).map((l) => (
          <span key={l} className="tabular block font-normal">
            {l}
          </span>
        ))}
      </span>
    </div>
  );
}

/** An evaluator slot the cascade did not need, drawn so every card reads left to right the same way. */
function EmptySlot({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed border-hairline-strong px-3.5 py-3">
      <div className="text-[0.8125rem] font-medium text-ink-3">{title}</div>
      <p className="mt-0.5 text-2xs text-ink-3">{body}</p>
    </div>
  );
}

function Chain({ m, caseData }: { m: MetricResult; caseData?: Case | null }) {
  const [primary, fallback] = m.judgments;
  const conf = primary?.confidence ?? null;
  const thr = m.escalate_below;
  const grid = "grid gap-2 lg:grid-cols-[minmax(0,1fr)_7rem_minmax(0,1fr)] lg:items-start lg:gap-3";

  if (m.route === "jev_to_llm" && primary && fallback) {
    const reason = m.escalation_reason;
    return (
      <div className={grid}>
        <JudgmentBlock caseData={caseData} j={primary} metric={m} showThreshold />
        <Connector
          tone="esc"
          title="Escalated"
          label="Escalated to the LLM judge"
          lines={[
            reason ? ESCALATION_REASON_LABEL[reason] : "to fallback",
            reason === "low_confidence" && conf !== null && thr !== null ? `${fmtNum(conf, 2)} < ${fmtNum(thr, 2)}` : null,
          ]}
        />
        <JudgmentBlock caseData={caseData} j={fallback} metric={m} showThreshold={false} />
      </div>
    );
  }
  if (m.route === "jev" && primary && m.judgments.length === 1) {
    return (
      <div className={grid}>
        <JudgmentBlock caseData={caseData} j={primary} metric={m} showThreshold />
        <Connector
          tone="jev"
          title="Accepted"
          label="Jev's answer accepted"
          lines={[conf !== null && thr !== null ? `${fmtNum(conf, 2)} ≥ ${fmtNum(thr, 2)}` : null]}
        />
        <EmptySlot title="LLM judge not called" body="Jev was confident enough, so no generative judge ran for this metric." />
      </div>
    );
  }
  if (m.route === "deterministic" && primary && m.judgments.length === 1) {
    return (
      <div className={grid}>
        <JudgmentBlock caseData={caseData} j={primary} metric={m} showThreshold={false} />
        <Connector tone="det" title="Settled by rule" label="Settled by a deterministic check" lines={["no model call"]} />
        <EmptySlot title="No model judges called" body="A rule-based check could decide this metric on its own." />
      </div>
    );
  }
  if (m.route === "llm" && primary && m.judgments.length === 1) {
    return (
      <div className={grid}>
        <EmptySlot
          title="Jev skipped"
          body={
            m.escalation_reason === "requires_reasoning" || !m.escalation_reason
              ? "This metric requires multi-step reasoning, so it goes straight to the LLM judge."
              : "The policy routes this metric straight to the LLM judge."
          }
        />
        <Connector tone="llm" title="Routed directly" label="Routed directly to the LLM judge" lines={["LLM judge only"]} />
        <JudgmentBlock caseData={caseData} j={primary} metric={m} showThreshold={false} />
      </div>
    );
  }
  // Anything else (custom evaluators, unusual shapes): list judgments in order.
  return (
    <div className="grid gap-2">
      {m.judgments.map((j, i) => (
        <JudgmentBlock caseData={caseData} key={i} j={j} metric={m} showThreshold={i === 0 && (m.route === "jev" || m.route === "jev_to_llm")} />
      ))}
    </div>
  );
}

export function MetricJudgmentCard({ metric: m, caseData }: { metric: MetricResult; caseData?: Case | null }) {
  return (
    <article id={`metric-${m.metric}`} className="scroll-mt-6 rounded-xl border border-hairline bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 pt-3.5 pb-3">
        <div className="min-w-0">
          <h3 className="text-[0.875rem] font-semibold text-ink">{m.display_name}</h3>
          <p className="text-2xs text-ink-3">
            <span className="font-mono">{m.metric}</span>
            <span className="ml-2">{CATEGORY_LABEL[m.category]}</span>
            <span className="ml-2">threshold {m.threshold.toFixed(2)}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="tabular text-lg leading-none font-semibold tracking-[-0.02em] text-ink">{fmtScore(m.score)}</span>
          <PassBadge passed={m.passed} />
          <RouteBadge route={m.route} />
          <span className="tabular text-2xs text-ink-3">
            {fmtMs(m.latency_ms)}, {fmtCost(m.cost_usd)}
          </span>
        </div>
      </header>

      <div className="border-t border-hairline bg-sunken/50 px-4 py-3.5">
        {m.status !== "ok" && (
          <div className="flex items-start gap-2 text-[0.8125rem] text-ink-2">
            {m.status === "error" ? (
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-bad-ink" aria-hidden />
            ) : (
              <CircleSlash className="mt-0.5 size-4 shrink-0 text-ink-3" aria-hidden />
            )}
            <p>
              <span className="font-medium text-ink">{m.status === "error" ? "Errored" : "Skipped"}.</span> {m.message ?? "No reason given."}
            </p>
          </div>
        )}
        {m.judgments.length > 0 && <Chain m={m} caseData={caseData} />}
      </div>
    </article>
  );
}
