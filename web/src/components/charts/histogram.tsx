import { cn } from "cn";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * 10-bin score distribution over [0, 1] with the pass threshold drawn in.
 * Bins that lie entirely below the threshold are tinted as failing.
 */
export function MiniHistogram({
  bins,
  threshold,
  className,
  height = 34,
}: {
  bins: number[];
  threshold?: number | null;
  className?: string;
  height?: number;
}) {
  const max = Math.max(1, ...bins);
  const total = bins.reduce((a, b) => a + b, 0);
  const label = `Score distribution: ${bins.map((b, i) => `${(i / 10).toFixed(1)} to ${((i + 1) / 10).toFixed(1)}: ${b}`).join("; ")}`;
  return (
    <div className={cn("relative w-full min-w-[7.5rem]", className)} style={{ height }} role="img" aria-label={label}>
      <div className="absolute inset-0 flex items-end gap-[2px]">
        {bins.map((b, i) => {
          // Only bins that lie entirely below the threshold are failing. The last bin
          // includes 1.0, so it can always hold passing scores.
          const failing = threshold !== null && threshold !== undefined && i < 9 && (i + 1) / 10 <= threshold + 1e-9;
          return (
            <Tooltip key={i}>
              <TooltipTrigger asChild>
                <span className="flex h-full flex-1 items-end">
                  <span
                    className="block w-full rounded-t-[2px]"
                    style={{
                      height: b === 0 ? 1 : `${Math.max(8, (b / max) * 100)}%`,
                      background: b === 0 ? "var(--hairline-strong)" : failing ? "color-mix(in oklab, var(--bad) 70%, var(--surface))" : "var(--ink-3)",
                    }}
                  />
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {(i / 10).toFixed(1)}–{((i + 1) / 10).toFixed(1)}: {b} case{b === 1 ? "" : "s"}
                {total > 0 ? ` (${Math.round((b / total) * 100)}%)` : ""}
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>
      {threshold !== null && threshold !== undefined && (
        <span
          aria-hidden
          className="pointer-events-none absolute -top-0.5 -bottom-0.5 w-0 border-l border-dashed border-ink"
          style={{ left: `${Math.min(1, Math.max(0, threshold)) * 100}%` }}
        />
      )}
    </div>
  );
}
