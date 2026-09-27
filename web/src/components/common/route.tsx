import { cn } from "cn";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { fmtInt, fmtPct } from "@/lib/format";
import { ROUTE_META, ROUTE_ORDER, routeTotal } from "@/lib/route-meta";
import type { Route, RouteCounts } from "@/lib/types";

export function RouteDot({ route, className }: { route: Route; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2 shrink-0 rounded-full", className)}
      style={{ background: ROUTE_META[route].color }}
    />
  );
}

/** Route label on a tint of its own color. Text uses the AA-safe "ink" companion. */
export function RouteBadge({ route, className, short }: { route: Route; className?: string; short?: boolean }) {
  const m = ROUTE_META[route];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn(
            "inline-flex h-5 shrink-0 cursor-default items-center gap-1.5 rounded-[5px] px-1.5 text-[0.6875rem] font-medium whitespace-nowrap",
            className,
          )}
          style={{
            color: m.ink,
            background: `color-mix(in oklab, ${m.color} 13%, var(--surface))`,
            boxShadow: `inset 0 0 0 1px color-mix(in oklab, ${m.color} 28%, transparent)`,
          }}
        >
          <RouteDot route={route} className="size-1.5" />
          {short ? m.short : m.label}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{m.description}</TooltipContent>
    </Tooltip>
  );
}

/** Stacked share of routes. Segments are separated by a 2px surface gap. */
export function RouteBar({
  counts,
  className,
  height = 8,
  includeNone = true,
}: {
  counts: RouteCounts;
  className?: string;
  height?: number;
  includeNone?: boolean;
}) {
  const order = includeNone ? ROUTE_ORDER : ROUTE_ORDER.filter((r) => r !== "none");
  const total = order.reduce((a, r) => a + counts[r], 0);
  if (total === 0) {
    return <div className={cn("rounded-full bg-sunken", className)} style={{ height }} aria-label="No evaluations" />;
  }
  const label = order
    .filter((r) => counts[r] > 0)
    .map((r) => `${ROUTE_META[r].label} ${counts[r]}`)
    .join(", ");
  return (
    <div className={cn("flex w-full gap-[2px]", className)} style={{ height }} role="img" aria-label={label}>
      {order
        .filter((r) => counts[r] > 0)
        .map((r) => (
          <Tooltip key={r}>
            <TooltipTrigger asChild>
              <span
                className="block h-full min-w-[3px] first:rounded-l-[3px] last:rounded-r-[3px]"
                style={{ flexGrow: counts[r], flexBasis: 0, background: ROUTE_META[r].color }}
              />
            </TooltipTrigger>
            <TooltipContent>
              {ROUTE_META[r].label}: {fmtInt(counts[r])} ({fmtPct(counts[r] / total)})
            </TooltipContent>
          </Tooltip>
        ))}
    </div>
  );
}

export function RouteLegend({
  counts,
  className,
  includeNone = false,
}: {
  counts?: RouteCounts;
  className?: string;
  includeNone?: boolean;
}) {
  const order = includeNone ? ROUTE_ORDER : ROUTE_ORDER.filter((r) => r !== "none");
  const total = counts ? routeTotal(counts) : 0;
  return (
    <ul className={cn("flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-2", className)}>
      {order.map((r) => (
        <li key={r} className="flex items-center gap-1.5">
          <RouteDot route={r} />
          <span>{ROUTE_META[r].label}</span>
          {counts && (
            <span className="tabular text-ink-3">
              {fmtInt(counts[r])}
              {total > 0 && ` (${fmtPct(counts[r] / total, 0)})`}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
