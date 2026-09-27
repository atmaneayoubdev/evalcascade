import { Info } from "lucide-react";
import { cn } from "cn";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * A row of measurements sharing one frame. Each cell draws a 1px outline into
 * the 1px grid gap, so the dividers hold up when the grid wraps and any unused
 * trailing space stays plain surface.
 */
export function KpiStrip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "grid gap-px overflow-hidden rounded-xl border border-hairline bg-surface",
        "grid-cols-2 sm:grid-cols-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Kpi({
  label,
  value,
  sub,
  hint,
  swatch,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  hint?: string;
  /** a route color marking what the number measures */
  swatch?: string;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 bg-surface px-4 py-3.5 shadow-[0_0_0_1px_var(--hairline)]", className)}>
      <div className="flex items-center gap-1.5 text-xs text-ink-3">
        {swatch && <span aria-hidden className="size-2 shrink-0 rounded-[2px]" style={{ background: swatch }} />}
        <span className="truncate">{label}</span>
        {hint && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button type="button" className="shrink-0 rounded-sm text-ink-3 hover:text-ink" aria-label={`About ${label}`}>
                <Info className="size-3" aria-hidden />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-64">{hint}</TooltipContent>
          </Tooltip>
        )}
      </div>
      <div className="mt-1 truncate text-[1.375rem] leading-7 font-medium tracking-[-0.02em] text-ink">{value}</div>
      {sub && <div className="mt-0.5 truncate text-xs text-ink-3">{sub}</div>}
    </div>
  );
}
