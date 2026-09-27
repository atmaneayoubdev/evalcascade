import { cn } from "cn";
import { fmtInt, fmtPct } from "@/lib/format";
import { ROUTE_META, ROUTE_ORDER } from "@/lib/route-meta";
import type { Route, RouteCounts } from "@/lib/types";

const ROW_NOTE: Record<Route, string> = {
  deterministic: "Rule-based check, no model call",
  jev: "Confident System One answer",
  jev_to_llm: "Jev unsure or failed; LLM decided",
  llm: "Reasoning metrics, LLM only",
  none: "Skipped or errored",
};

/**
 * The routing cascade: a horizontal waterfall of every metric evaluation.
 * Each tier starts where the cheaper tier above it stopped, so the eye walks
 * down the same path a judgment takes: rules, then Jev, then the LLM judge.
 */
export function RoutingCascade({ counts, className }: { counts: RouteCounts; className?: string }) {
  const rows = ROUTE_ORDER.filter((r) => r !== "none" || counts.none > 0);
  const total = rows.reduce((a, r) => a + counts[r], 0);
  const judged = total - counts.none;
  const withoutLlm = counts.deterministic + counts.jev;
  const share = judged > 0 ? withoutLlm / judged : null;

  const widths = rows.map((r) => (total > 0 ? counts[r] / total : 0));
  const geometry = rows.map((r, i) => ({
    route: r,
    left: widths.slice(0, i).reduce((a, b) => a + b, 0),
    width: widths[i],
  }));

  return (
    <div className={cn("min-w-0", className)}>
      <div className="mb-5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[2rem] leading-none font-semibold tracking-[-0.03em] text-ink">
          {share === null ? "—" : fmtPct(share, 0)}
        </span>
        <span className="max-w-[46ch] text-[0.8125rem] text-ink-2">
          of {fmtInt(judged)} judgments were settled without calling an LLM judge.
        </span>
      </div>

      <ol className="space-y-0" aria-label="Where each judgment was decided">
        {geometry.map((g, i) => {
          const m = ROUTE_META[g.route];
          const n = counts[g.route];
          return (
            <li
              key={g.route}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 sm:grid-cols-[15rem_minmax(0,1fr)_5.5rem]"
            >
              <div className="col-span-2 flex min-w-0 items-center gap-2 pt-1.5 sm:col-span-1 sm:pt-0">
                <span aria-hidden className="size-2.5 shrink-0 rounded-[3px]" style={{ background: m.color }} />
                <span className="min-w-0">
                  <span className="block truncate text-[0.8125rem] font-medium text-ink">{m.label}</span>
                  <span className="block truncate text-2xs text-ink-3">{ROW_NOTE[g.route]}</span>
                </span>
              </div>
              <div className="relative h-9" aria-hidden>
                {/* baseline track */}
                <div className="absolute inset-x-0 top-1/2 h-px bg-hairline" />
                {/* connector from the tier above */}
                {i > 0 && (
                  <div
                    className="absolute w-0 border-l border-dashed border-ink-3/60"
                    style={{ left: `${g.left * 100}%`, top: "-0.5rem", height: "1.1rem" }}
                  />
                )}
                {n > 0 && (
                  <div
                    className="absolute top-1/2 h-3.5 -translate-y-1/2 rounded-[3px]"
                    style={{
                      left: `${g.left * 100}%`,
                      width: `max(3px, calc(${g.width * 100}% - 2px))`,
                      background: m.color,
                    }}
                  />
                )}
              </div>
              <div className="tabular text-right text-[0.8125rem] leading-tight">
                <span className="block font-medium text-ink">{fmtInt(n)}</span>
                <span className="block text-2xs text-ink-3">{total > 0 ? fmtPct(n / total) : "—"}</span>
              </div>
            </li>
          );
        })}
      </ol>
      <div className="mt-1 hidden grid-cols-[15rem_minmax(0,1fr)_5.5rem] gap-x-4 text-2xs text-ink-3 sm:grid" aria-hidden>
        <span />
        <span className="flex justify-between">
          <span>0</span>
          <span>{fmtInt(total)} metric evaluations</span>
        </span>
        <span />
      </div>
    </div>
  );
}
