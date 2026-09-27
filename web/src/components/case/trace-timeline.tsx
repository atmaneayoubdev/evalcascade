"use client";

import { Brain, Check, MessageSquare, Wrench, X } from "lucide-react";
import { cn } from "cn";
import { JsonBlock } from "@/components/common/code";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { fmtMs, humanize } from "@/lib/format";
import type { AgentTrace, MetricResult, StepJudgment, TraceStep } from "@/lib/types";

export interface StepBadge {
  metric: string;
  displayName: string;
  threshold: number;
  judgment: StepJudgment;
}

/** Collect per-step judgments from every metric's `details.steps`, keyed by step index. */
export function collectStepBadges(metrics: MetricResult[]): Map<number, StepBadge[]> {
  const out = new Map<number, StepBadge[]>();
  for (const m of metrics) {
    const steps = Array.isArray(m.details?.steps) ? m.details.steps : [];
    for (const s of steps) {
      if (typeof s?.step_index !== "number") continue;
      const list = out.get(s.step_index) ?? [];
      list.push({ metric: m.metric, displayName: m.display_name, threshold: m.threshold, judgment: s });
      out.set(s.step_index, list);
    }
  }
  return out;
}

const TYPE_META: Record<TraceStep["type"], { label: string; Icon: typeof Brain }> = {
  thought: { label: "Thought", Icon: Brain },
  tool_call: { label: "Tool call", Icon: Wrench },
  message: { label: "Message", Icon: MessageSquare },
};

function Badge({ b }: { b: StepBadge }) {
  const s = b.judgment.score;
  const ok = s === null ? null : s >= b.threshold - 1e-9;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn(
            "inline-flex h-5 cursor-default items-center gap-1 rounded-[5px] px-1.5 text-2xs font-medium",
            ok === true && "text-good-ink",
            ok === false && "text-bad-ink",
            ok === null && "text-ink-2",
          )}
          style={{
            background:
              ok === null
                ? "var(--sunken)"
                : `color-mix(in oklab, var(${ok ? "--good" : "--bad"}) 11%, var(--surface))`,
          }}
        >
          {ok === true && <Check className="size-3" aria-hidden />}
          {ok === false && <X className="size-3" aria-hidden />}
          <span className="text-ink-3">{b.displayName}:</span>
          {humanize(b.judgment.label)}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-72">
        <span className="block font-medium">
          {b.displayName}: {humanize(b.judgment.label)}
          {s !== null && ` (${s.toFixed(2)})`}
        </span>
        {b.judgment.explanation && <span className="block opacity-85">{b.judgment.explanation}</span>}
      </TooltipContent>
    </Tooltip>
  );
}

function StepBody({ step }: { step: TraceStep }) {
  const tc = step.tool_call;
  return (
    <div className="space-y-2">
      {step.content && (
        <p className={cn("text-[0.8125rem] leading-relaxed whitespace-pre-wrap", step.type === "thought" ? "text-ink-2" : "text-ink")}>
          {step.content}
        </p>
      )}
      {tc && (
        <div className="grid gap-2 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="mb-1 text-2xs text-ink-3">Arguments</div>
            <JsonBlock value={tc.arguments} maxHeight={220} />
          </div>
          <div className="min-w-0">
            <div className="mb-1 text-2xs text-ink-3">{tc.error ? "Error" : "Result"}</div>
            {tc.error ? (
              <pre
                className="overflow-auto rounded-lg border px-3 py-2.5 font-mono text-xs leading-5 whitespace-pre-wrap text-bad-ink"
                style={{
                  background: "color-mix(in oklab, var(--bad) 7%, var(--surface))",
                  borderColor: "color-mix(in oklab, var(--bad) 30%, transparent)",
                }}
              >
                {tc.error}
              </pre>
            ) : tc.result === null || tc.result === undefined ? (
              <p className="text-xs text-ink-3">No result recorded.</p>
            ) : (
              <JsonBlock value={tc.result} maxHeight={220} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Vertical timeline of an agent trace, with every metric's per-step verdicts attached. */
export function TraceTimeline({ trace, metrics }: { trace: AgentTrace; metrics: MetricResult[] }) {
  const badges = collectStepBadges(metrics);
  const total = trace.steps.reduce((a, s) => a + (s.latency_ms ?? 0), 0);
  return (
    <div>
      <p className="mb-3 text-xs text-ink-3">
        {trace.steps.length} steps, {trace.steps.filter((s) => s.type === "tool_call").length} tool calls
        {total > 0 && `, ${fmtMs(total)} total`}
      </p>
      <ol className="relative">
        {trace.steps.map((step, i) => {
          const meta = TYPE_META[step.type];
          const failed = Boolean(step.tool_call?.error);
          const stepBadges = badges.get(i) ?? [];
          return (
            <li key={i} className="relative grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3 pb-5 last:pb-0">
              {i < trace.steps.length - 1 && (
                <span aria-hidden className="absolute top-8 bottom-0 left-4 w-px -translate-x-1/2 bg-hairline-strong" />
              )}
              <span
                className={cn(
                  "relative z-10 grid size-8 place-items-center rounded-full border bg-surface",
                  failed ? "border-bad/50 text-bad-ink" : "border-hairline-strong text-ink-2",
                )}
                aria-hidden
              >
                <meta.Icon className="size-3.5" />
              </span>
              <div className="min-w-0 pt-1">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span className="tabular text-2xs font-medium text-ink-3">Step {i + 1}</span>
                  <span className="text-[0.8125rem] font-medium text-ink">{meta.label}</span>
                  {step.tool_call && (
                    <code className="rounded-[4px] bg-sunken px-1.5 py-px font-mono text-xs text-ink">{step.tool_call.name}</code>
                  )}
                  {failed && <span className="text-2xs font-medium text-bad-ink">failed</span>}
                  {step.latency_ms !== null && <span className="tabular ml-auto text-2xs text-ink-3">{fmtMs(step.latency_ms)}</span>}
                </div>
                {stepBadges.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {stepBadges.map((b) => (
                      <Badge key={b.metric} b={b} />
                    ))}
                  </div>
                )}
                <div className="mt-2">
                  <StepBody step={step} />
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
