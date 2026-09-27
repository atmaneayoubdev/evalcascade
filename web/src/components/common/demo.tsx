import { cn } from "cn";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Cmd } from "./code";

/** Every synthetic experiment wears this badge, everywhere it appears. */
export function DemoBadge({ className }: { className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          aria-label="Demo: synthetic demonstration data, not a real evaluation"
          className={cn(
            "hatch inline-flex h-[18px] shrink-0 cursor-default items-center rounded-[4px] border border-ink-3/45 px-1.5 text-[0.625rem] leading-none font-semibold tracking-[0.07em] text-ink-2",
            className,
          )}
        >
          DEMO
        </span>
      </TooltipTrigger>
      <TooltipContent>Synthetic demonstration data, not a real evaluation.</TooltipContent>
    </Tooltip>
  );
}

/** Non-interactive variant for use inside menus, tooltips and chart labels. */
export function DemoTag({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "hatch inline-flex h-4 shrink-0 items-center rounded-[3px] border border-ink-3/45 px-1 text-[0.5625rem] leading-none font-semibold tracking-[0.07em] text-ink-2",
        className,
      )}
    >
      DEMO
    </span>
  );
}

export function DemoMaybe({ isDemo, className }: { isDemo: boolean; className?: string }) {
  return isDemo ? <DemoBadge className={className} /> : null;
}

export function DemoBanner({ variant = "global", className }: { variant?: "global" | "experiment" | "mixed"; className?: string }) {
  return (
    <div
      role="note"
      className={cn(
        "relative mb-6 flex items-start gap-3 overflow-hidden rounded-xl border border-hairline-strong bg-surface py-3 pr-4 pl-5",
        className,
      )}
    >
      <span aria-hidden className="hatch absolute inset-y-0 left-0 w-2 border-r border-hairline-strong" />
      <DemoBadge className="mt-px" />
      <p className="text-[0.8125rem] text-ink-2">
        {variant === "global" && (
          <>
            Showing demonstration data — run <Cmd>evalcascade run &lt;dataset&gt;</Cmd> to record real evaluations.
          </>
        )}
        {variant === "experiment" && (
          <>
            This experiment is synthetic demonstration data. Its scores, costs and latencies were generated, not measured. Run{" "}
            <Cmd>evalcascade run &lt;dataset&gt;</Cmd> to record a real evaluation.
          </>
        )}
        {variant === "mixed" && (
          <>Demo experiments are included below and marked with a DEMO badge. Their numbers are synthetic.</>
        )}
      </p>
    </div>
  );
}
