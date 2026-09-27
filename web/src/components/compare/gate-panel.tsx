"use client";

import { useId, useState } from "react";
import { CircleCheck, CircleX, Loader2, ShieldCheck } from "lucide-react";
import { cn } from "cn";
import { Panel } from "@/components/common/layout";
import { ErrorState } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { api, toApiError, type ApiError } from "@/lib/api";
import { fmtPct, fmtRelative, fmtScore, fmtSigned } from "@/lib/format";
import type { Comparison, GateCheck, GateRequest, GateResult } from "@/lib/types";

function Field({
  label,
  hint,
  value,
  onChange,
  placeholder,
  suffix,
  error,
  step = "0.01",
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  suffix?: string;
  error?: string | null;
  step?: string;
}) {
  const id = useId();
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="block text-xs font-medium text-ink-2">
        {label}
      </label>
      {hint && <p className="text-2xs text-ink-3">{hint}</p>}
      <div className="relative mt-1">
        <Input
          id={id}
          type="number"
          inputMode="decimal"
          step={step}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-invalid={error ? true : undefined}
          className={cn("tabular h-8 bg-surface text-[0.8125rem]", suffix && "pr-8")}
        />
        {suffix && <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-xs text-ink-3">{suffix}</span>}
      </div>
      {error && <p className="mt-1 text-2xs text-bad-ink">{error}</p>}
    </div>
  );
}

const parse = (s: string): number | null => {
  if (s.trim() === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : Number.NaN;
};

function checkLabel(c: GateCheck, names: Record<string, string>) {
  if (c.name === "overall_score") return "Overall score";
  if (c.name.startsWith("metric:")) {
    const m = c.name.slice(7);
    return names[m] ?? m;
  }
  if (c.name === "cost") return "Total cost";
  if (c.name === "latency_p95") return "Latency p95";
  if (c.name === "min_score") return "Minimum overall score";
  if (c.name === "escalation_rate") return "Escalation rate";
  if (c.name === "dataset") return "Same dataset";
  return c.name;
}

/**
 * Formats a check the way the backend reports it: drop checks carry
 * actual = baseline - candidate (positive = worse) and limit = allowed drop;
 * cost/latency carry a relative increase; escalation carries a rate.
 */
function checkValues(c: GateCheck): { actual: string; limit: string } {
  if (c.name === "overall_score" || c.name.startsWith("metric:"))
    return {
      actual: c.actual === null ? "n/a" : `change ${fmtSigned(-c.actual)}`,
      limit: `max drop ${fmtScore(c.limit)}`,
    };
  if (c.name === "cost" || c.name === "latency_p95") return { actual: fmtRelative(c.actual), limit: `≤ ${fmtRelative(c.limit)}` };
  if (c.name === "min_score") return { actual: fmtScore(c.actual), limit: `≥ ${fmtScore(c.limit)}` };
  if (c.name === "escalation_rate") return { actual: fmtPct(c.actual), limit: `≤ ${fmtPct(c.limit)}` };
  if (c.name === "dataset") return { actual: c.passed ? "same" : "different", limit: "must match" };
  return { actual: c.actual === null ? "—" : String(c.actual), limit: String(c.limit) };
}

/** Inline regression gate: the same check CI runs, against this pair. */
export function GatePanel({ cmp, metricNames }: { cmp: Comparison; metricNames: Record<string, string> }) {
  const [maxDrop, setMaxDrop] = useState("0.03");
  const [metricThr, setMetricThr] = useState<Record<string, string>>({});
  const [maxCost, setMaxCost] = useState("");
  const [maxLatency, setMaxLatency] = useState("");
  const [minScore, setMinScore] = useState("");
  const [metricDefault, setMetricDefault] = useState("");
  const [maxEscalation, setMaxEscalation] = useState("");
  const [sameDataset, setSameDataset] = useState(false);
  const [result, setResult] = useState<GateResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  const drop = parse(maxDrop);
  const dropError = drop === null ? "Required." : Number.isNaN(drop) || drop < 0 || drop > 1 ? "Between 0 and 1." : null;
  const metricErrors = Object.fromEntries(
    Object.entries(metricThr).map(([m, v]) => {
      const n = parse(v);
      return [m, n !== null && (Number.isNaN(n) || n < 0 || n > 1) ? "Between 0 and 1." : null];
    }),
  );
  const cost = parse(maxCost);
  const latency = parse(maxLatency);
  const floor = parse(minScore);
  const costError = cost !== null && (Number.isNaN(cost) || cost < 0) ? "Zero or more." : null;
  const latencyError = latency !== null && (Number.isNaN(latency) || latency < 0) ? "Zero or more." : null;
  const floorError = floor !== null && (Number.isNaN(floor) || floor < 0 || floor > 1) ? "Between 0 and 1." : null;
  const defaultDrop = parse(metricDefault);
  const defaultDropError = defaultDrop !== null && (Number.isNaN(defaultDrop) || defaultDrop < 0 || defaultDrop > 1) ? "Between 0 and 1." : null;
  const escalation = parse(maxEscalation);
  const escalationError = escalation !== null && (Number.isNaN(escalation) || escalation < 0 || escalation > 100) ? "0 to 100." : null;
  const invalid = Boolean(
    dropError || costError || latencyError || floorError || defaultDropError || escalationError || Object.values(metricErrors).some(Boolean),
  );

  const run = async () => {
    if (invalid || drop === null) return;
    const thresholds: Record<string, number> = {};
    for (const [m, v] of Object.entries(metricThr)) {
      const n = parse(v);
      if (n !== null && !Number.isNaN(n)) thresholds[m] = n;
    }
    const req: GateRequest = {
      baseline: cmp.baseline.id,
      candidate: cmp.candidate.id,
      max_quality_drop: drop,
      ...(Object.keys(thresholds).length ? { metric_thresholds: thresholds } : {}),
      ...(cost !== null ? { max_cost_increase: cost / 100 } : {}),
      ...(latency !== null ? { max_latency_increase: latency / 100 } : {}),
      ...(floor !== null ? { min_score: floor } : {}),
      ...(defaultDrop !== null ? { max_metric_drop: defaultDrop } : {}),
      ...(escalation !== null ? { max_escalation_rate: escalation / 100 } : {}),
      ...(sameDataset ? { require_same_dataset: true } : {}),
    };
    setBusy(true);
    setError(null);
    try {
      setResult(await api.gate(req));
    } catch (e) {
      setResult(null);
      setError(toApiError(e, "/gate"));
    } finally {
      setBusy(false);
    }
  };

  const metrics = Object.keys(cmp.metrics);

  return (
    <Panel
      title="Regression gate"
      description="Run the gate CI would run on this pair. It fails when the candidate drops more than you allow."
    >
      <div className="grid gap-0 border-t border-hairline lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <form
          className="space-y-4 px-4 py-4 lg:border-r lg:border-hairline"
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
        >
          <Field
            label="Max overall score drop"
            hint="Absolute, on the 0–1 score scale."
            value={maxDrop}
            onChange={setMaxDrop}
            error={dropError}
            step="0.005"
          />
          {metrics.length > 0 && (
            <fieldset>
              <legend className="text-xs font-medium text-ink-2">Per-metric max drop</legend>
              <p className="text-2xs text-ink-3">Optional. A default applies to every metric; a per-metric value overrides it.</p>
              <div className="mt-2 grid items-end gap-x-3 gap-y-2 sm:grid-cols-2">
                <Field
                  label="Default for all metrics"
                  value={metricDefault}
                  onChange={setMetricDefault}
                  placeholder="—"
                  error={defaultDropError}
                  step="0.005"
                />
                {metrics.map((m) => (
                  <Field
                    key={m}
                    label={metricNames[m] ?? m}
                    value={metricThr[m] ?? ""}
                    onChange={(v) => setMetricThr((s) => ({ ...s, [m]: v }))}
                    placeholder="—"
                    error={metricErrors[m]}
                    step="0.005"
                  />
                ))}
              </div>
            </fieldset>
          )}
          <div className="grid items-end gap-x-3 gap-y-2 sm:grid-cols-2">
            <Field label="Max cost increase" value={maxCost} onChange={setMaxCost} placeholder="—" suffix="%" error={costError} step="1" />
            <Field label="Max p95 increase" value={maxLatency} onChange={setMaxLatency} placeholder="—" suffix="%" error={latencyError} step="1" />
            <Field label="Min overall score" value={minScore} onChange={setMinScore} placeholder="—" error={floorError} />
            <Field
              label="Max escalation rate"
              value={maxEscalation}
              onChange={setMaxEscalation}
              placeholder="—"
              suffix="%"
              error={escalationError}
              step="1"
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-ink-2 select-none">
            <Checkbox checked={sameDataset} onCheckedChange={(v) => setSameDataset(v === true)} />
            Fail when the two experiments used different datasets
          </label>
          <Button type="submit" disabled={invalid || busy} className="w-full sm:w-auto">
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : <ShieldCheck aria-hidden />}
            {busy ? "Running gate…" : "Run gate"}
          </Button>
        </form>

        <div className="min-w-0 px-4 py-4" aria-live="polite">
          {error ? (
            <ErrorState error={error} onRetry={() => void run()} className="border-0 p-0 sm:p-0" />
          ) : !result ? (
            <div className="grid h-full min-h-40 place-items-center rounded-lg border border-dashed border-hairline-strong px-6 text-center text-xs text-ink-3">
              Set the limits and run the gate to see each check.
            </div>
          ) : (
            <GateOutcome result={result} names={metricNames} />
          )}
        </div>
      </div>
    </Panel>
  );
}

function GateOutcome({ result, names }: { result: GateResult; names: Record<string, string> }) {
  const passedCount = result.checks.filter((c) => c.passed).length;
  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-3 rounded-lg px-3.5 py-3",
          result.passed ? "text-good-ink" : "text-bad-ink",
        )}
        style={{ background: `color-mix(in oklab, var(${result.passed ? "--good" : "--bad"}) 10%, var(--surface))` }}
      >
        {result.passed ? <CircleCheck className="size-5 shrink-0" aria-hidden /> : <CircleX className="size-5 shrink-0" aria-hidden />}
        <div>
          <div className="text-sm font-semibold">{result.passed ? "Gate passed" : "Gate failed"}</div>
          <div className="text-xs opacity-90">
            {passedCount} of {result.checks.length} checks passed
            {result.violations.length > 0 && `, ${result.violations.length} violation${result.violations.length > 1 ? "s" : ""}`}
          </div>
        </div>
      </div>
      <ul className="mt-3 divide-y divide-hairline rounded-lg border border-hairline">
        {result.checks.map((c) => {
          const v = checkValues(c);
          return (
            <li key={c.name} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 px-3 py-2.5">
              {c.passed ? (
                <CircleCheck className="mt-0.5 size-4 text-good-ink" aria-label="Passed" />
              ) : (
                <CircleX className="mt-0.5 size-4 text-bad-ink" aria-label="Failed" />
              )}
              <div className="min-w-0">
                <div className="text-[0.8125rem] font-medium text-ink">{checkLabel(c, names)}</div>
                <p className="text-xs text-ink-3">{c.message}</p>
              </div>
              <div className="tabular text-right text-xs">
                <div className={cn("font-medium", c.passed ? "text-ink" : "text-bad-ink")}>{v.actual}</div>
                <div className="text-ink-3">limit {v.limit}</div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
