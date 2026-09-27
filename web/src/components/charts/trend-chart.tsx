"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import { cn } from "cn";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fmtDateTime, fmtPct, fmtScore, fmtShortDate } from "@/lib/format";
import type { TrendPoint } from "@/lib/types";
import { urls } from "@/lib/urls";

type Mode = "quality" | "routing";

interface Series {
  key: keyof TrendPoint;
  label: string;
  color: string;
  dash?: string;
  format: (v: number | null) => string;
}

const SERIES: Record<Mode, Series[]> = {
  quality: [
    { key: "overall_score", label: "Overall score", color: "var(--ink)", format: (v) => fmtScore(v) },
    { key: "pass_rate", label: "Pass rate", color: "var(--ink-3)", dash: "5 4", format: (v) => fmtPct(v) },
  ],
  routing: [
    { key: "jev_acceptance_rate", label: "Jev acceptance", color: "var(--route-jev)", format: (v) => fmtPct(v) },
    { key: "escalation_rate", label: "Escalated to LLM", color: "var(--route-esc)", format: (v) => fmtPct(v) },
  ],
};

interface Row extends TrendPoint {
  idx: number;
}

function TrendTooltip({ active, payload, mode }: TooltipContentProps<number, string> & { mode: Mode }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as Row;
  return (
    <div className="min-w-44 rounded-lg border border-hairline bg-popover px-3 py-2 text-xs shadow-md">
      <div className="flex items-center gap-2">
        <span className="font-medium text-ink">{p.name}</span>
        {p.is_demo && (
          <span className="hatch rounded-[3px] border border-ink-3/45 px-1 text-[0.5625rem] font-semibold tracking-[0.07em] text-ink-2">
            DEMO
          </span>
        )}
      </div>
      <div className="mb-1.5 text-ink-3">
        {p.dataset_name ?? "no dataset"}, {fmtDateTime(p.created_at)}
      </div>
      {SERIES[mode].map((s) => (
        <div key={s.key} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-2">
            <svg width="14" height="4" aria-hidden>
              <line x1="0" y1="2" x2="14" y2="2" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} />
            </svg>
            {s.label}
          </span>
          <span className="tabular font-medium text-ink">{s.format(p[s.key] as number | null)}</span>
        </div>
      ))}
    </div>
  );
}

const ALL = "__all__";
const NONE = "__none__";
const datasetKey = (p: TrendPoint) => p.dataset_name ?? NONE;

/**
 * Quality (or routing) per experiment over time. Hollow points are demo experiments.
 * Experiments on different datasets aren't directly comparable, so the chart can be
 * narrowed to one dataset.
 */
export function TrendChart({ points, className }: { points: TrendPoint[]; className?: string }) {
  const [mode, setMode] = useState<Mode>("quality");
  const [picked, setPicked] = useState<string>(ALL);
  const router = useRouter();

  const datasets = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of points) counts.set(datasetKey(p), (counts.get(datasetKey(p)) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [points]);
  // If the selected dataset disappears (e.g. demo data hidden), fall back to all.
  const dataset = picked === ALL || datasets.some(([k]) => k === picked) ? picked : ALL;
  const data: Row[] = points.filter((p) => dataset === ALL || datasetKey(p) === dataset).map((p, idx) => ({ ...p, idx }));
  const series = SERIES[mode];

  return (
    <div className={cn("min-w-0", className)}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2" aria-label="Legend">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <svg width="18" height="4" aria-hidden>
                <line x1="0" y1="2" x2="18" y2="2" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} />
              </svg>
              {s.label}
            </li>
          ))}
          {points.some((p) => p.is_demo) && (
            <li className="flex items-center gap-1.5 text-ink-3">
              <svg width="10" height="10" aria-hidden>
                <circle cx="5" cy="5" r="3.5" fill="var(--surface)" stroke="var(--ink-3)" strokeWidth="1.5" />
              </svg>
              Demo experiment
            </li>
          )}
        </ul>
        <div className="flex flex-wrap items-center gap-2">
        {datasets.length > 1 && (
          <Select value={dataset} onValueChange={setPicked}>
            <SelectTrigger size="sm" className="h-7 min-w-40 bg-surface text-xs" aria-label="Dataset">
              <SelectValue />
            </SelectTrigger>
            <SelectContent position="popper" align="end">
              <SelectItem value={ALL}>All datasets ({points.length})</SelectItem>
              {datasets.map(([k, n]) => (
                <SelectItem key={k} value={k}>
                  {k === NONE ? "No dataset" : k} ({n})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <div role="tablist" aria-label="Trend measure" className="inline-flex rounded-md border border-hairline bg-sunken p-0.5 text-xs">
          {(["quality", "routing"] as Mode[]).map((m) => (
            <button
              key={m}
              role="tab"
              type="button"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={cn(
                "rounded-[5px] px-2.5 py-1 font-medium capitalize text-ink-3 transition-colors hover:text-ink",
                mode === m && "bg-surface text-ink shadow-[0_0_0_1px_var(--hairline)]",
              )}
            >
              {m}
            </button>
          ))}
        </div>
        </div>
      </div>
      <div className="h-[240px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="idx"
              type="number"
              domain={[-0.3, Math.max(0.3, data.length - 0.7)]}
              ticks={data.map((d) => d.idx)}
              tickFormatter={(i: number) => fmtShortDate(data[i]?.created_at)}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
              axisLine={{ stroke: "var(--chart-axis)" }}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={18}
            />
            <YAxis
              domain={[0, 1]}
              ticks={[0, 0.25, 0.5, 0.75, 1]}
              tickFormatter={(v: number) => (mode === "quality" ? v.toFixed(2) : `${Math.round(v * 100)}%`)}
              tick={{ fill: "var(--ink-3)", fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={44}
            />
            <Tooltip
              content={(props) => <TrendTooltip {...(props as TooltipContentProps<number, string>)} mode={mode} />}
              cursor={{ stroke: "var(--hairline-strong)", strokeWidth: 1 }}
            />
            {series.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={2}
                strokeDasharray={s.dash}
                connectNulls
                isAnimationActive={false}
                dot={(props: { cx?: number; cy?: number; index?: number; payload?: Row }) => {
                  const { cx, cy, payload, index } = props;
                  if (cx === undefined || cy === undefined || !payload) return <g key={`d-${s.key}-${index}`} />;
                  return (
                    <circle
                      key={`d-${s.key}-${index}`}
                      cx={cx}
                      cy={cy}
                      r={4}
                      fill={payload.is_demo ? "var(--surface)" : s.color}
                      stroke={s.color}
                      strokeWidth={1.75}
                    />
                  );
                }}
                activeDot={{
                  r: 6,
                  stroke: "var(--surface)",
                  strokeWidth: 2,
                  fill: s.color,
                  cursor: "pointer",
                  onClick: (_: unknown, e: unknown) => {
                    const idx = (e as { payload?: Row })?.payload?.idx;
                    const id = idx !== undefined ? data[idx]?.id : undefined;
                    if (id) router.push(urls.experiment(id));
                  },
                }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="sr-only">
        {data.map((d) => `${d.name}: overall ${fmtScore(d.overall_score)}, pass rate ${fmtPct(d.pass_rate)}`).join(". ")}
      </p>
    </div>
  );
}
