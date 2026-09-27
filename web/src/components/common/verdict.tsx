import { ArrowDownRight, ArrowUpRight, Check, Minus, X } from "lucide-react";
import { cn } from "cn";

export type Better = "higher" | "lower";
export type Tone = "good" | "bad" | "neutral";

/** Good/bad convention: for quality a rise is good; for cost, latency and escalation a fall is good. */
export function deltaTone(delta: number | null | undefined, better: Better, epsilon = 1e-9): Tone {
  if (delta === null || delta === undefined || !Number.isFinite(delta) || Math.abs(delta) <= epsilon) return "neutral";
  const up = delta > 0;
  return (better === "higher") === up ? "good" : "bad";
}

export const TONE_TEXT: Record<Tone, string> = {
  good: "text-good-ink",
  bad: "text-bad-ink",
  neutral: "text-ink-3",
};

/** A signed change with direction arrow and good/bad color (never color alone). */
export function DeltaText({
  delta,
  better,
  children,
  className,
  epsilon,
}: {
  delta: number | null | undefined;
  better: Better;
  children: React.ReactNode;
  className?: string;
  epsilon?: number;
}) {
  const tone = deltaTone(delta, better, epsilon);
  const Icon = tone === "neutral" ? Minus : (delta ?? 0) > 0 ? ArrowUpRight : ArrowDownRight;
  const word = tone === "good" ? "better" : tone === "bad" ? "worse" : "unchanged";
  return (
    <span className={cn("tabular inline-flex items-center gap-0.5 font-medium", TONE_TEXT[tone], className)}>
      <Icon className="size-3.5 shrink-0" aria-hidden />
      <span>{children}</span>
      <span className="sr-only"> ({word})</span>
    </span>
  );
}

export function PassBadge({ passed, className }: { passed: boolean | null | undefined; className?: string }) {
  if (passed === null || passed === undefined) {
    return <span className={cn("inline-flex h-5 items-center rounded-[5px] px-1.5 text-[0.6875rem] text-ink-3", className)}>n/a</span>;
  }
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1 rounded-[5px] px-1.5 text-[0.6875rem] font-medium",
        passed ? "text-good-ink" : "text-bad-ink",
        className,
      )}
      style={{
        background: `color-mix(in oklab, var(${passed ? "--good" : "--bad"}) 12%, var(--surface))`,
      }}
    >
      {passed ? <Check className="size-3" aria-hidden /> : <X className="size-3" aria-hidden />}
      {passed ? "Pass" : "Fail"}
    </span>
  );
}

/**
 * Score on a 0..1 track with the pass threshold drawn as a tick.
 * `tone` colors the fill by verdict; the default is neutral ink.
 */
export function ScoreBar({
  value,
  threshold,
  tone = "neutral",
  className,
  label,
}: {
  value: number | null | undefined;
  threshold?: number | null;
  tone?: Tone;
  className?: string;
  label?: string;
}) {
  const v = value === null || value === undefined ? null : Math.max(0, Math.min(1, value));
  const fill = tone === "good" ? "var(--good)" : tone === "bad" ? "var(--bad)" : "var(--ink-2)";
  return (
    <div
      className={cn("relative h-3 w-full", className)}
      role="img"
      aria-label={label ?? `Score ${v === null ? "n/a" : v.toFixed(3)}${threshold != null ? `, pass threshold ${threshold.toFixed(2)}` : ""}`}
    >
      <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 overflow-hidden rounded-full bg-sunken shadow-[inset_0_0_0_1px_var(--hairline)]">
        {v !== null && <div className="h-full rounded-full" style={{ width: `${v * 100}%`, background: fill }} />}
      </div>
      {threshold !== null && threshold !== undefined && (
        <div
          aria-hidden
          className="absolute top-0 h-3 w-[2px] -translate-x-1/2 rounded-full bg-ink"
          style={{ left: `${Math.max(0, Math.min(1, threshold)) * 100}%` }}
        />
      )}
    </div>
  );
}
