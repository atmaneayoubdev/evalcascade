"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from "recharts";
import { fmtScore, fmtSigned } from "@/lib/format";
import { deltaTone } from "@/components/common/verdict";

export interface MetricDeltaRow {
  metric: string;
  label: string;
  baseline: number | null;
  candidate: number | null;
  delta: number;
}

const TONE_FILL = {
  good: "var(--good)",
  bad: "var(--bad)",
  neutral: "var(--route-none)",
} as const;

function DeltaTooltip({ active, payload }: TooltipContentProps<number, string>) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as MetricDeltaRow;
  return (
    <div className="rounded-lg border border-hairline bg-popover px-3 py-2 text-xs shadow-md">
      <div className="mb-1 font-medium text-ink">{row.label}</div>
      <div className="tabular grid grid-cols-[auto_auto] gap-x-4 text-ink-2">
        <span>Baseline</span>
        <span className="text-right">{fmtScore(row.baseline)}</span>
        <span>Candidate</span>
        <span className="text-right">{fmtScore(row.candidate)}</span>
        <span>Change</span>
        <span className="text-right font-medium text-ink">{fmtSigned(row.delta)}</span>
      </div>
    </div>
  );
}

/** Diverging bars: per-metric mean score change, green when it improved, red when it dropped. */
export function MetricDeltaChart({ rows }: { rows: MetricDeltaRow[] }) {
  const max = Math.max(0.02, ...rows.map((r) => Math.abs(r.delta)));
  const lim = Math.ceil(max * 1.35 * 100) / 100;
  const height = Math.max(120, rows.length * 34 + 40);
  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 56, bottom: 4, left: 4 }} barCategoryGap={9}>
          <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
          <XAxis
            type="number"
            domain={[-lim, lim]}
            tickFormatter={(v: number) => fmtSigned(v, 2)}
            tick={{ fill: "var(--ink-3)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="label"
            width={150}
            tick={{ fill: "var(--ink-2)", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <ReferenceLine x={0} stroke="var(--chart-axis)" />
          <Tooltip content={(p) => <DeltaTooltip {...(p as TooltipContentProps<number, string>)} />} cursor={{ fill: "var(--sunken)" }} />
          <Bar dataKey="delta" radius={3} isAnimationActive={false} maxBarSize={18}>
            {rows.map((r) => (
              <Cell key={r.metric} fill={TONE_FILL[deltaTone(r.delta, "higher", 0.0005)]} />
            ))}
            <LabelList
              dataKey="delta"
              content={(props) => {
                const x = Number(props.x ?? 0);
                const y = Number(props.y ?? 0);
                const w = Number(props.width ?? 0);
                const h = Number(props.height ?? 0);
                const v = typeof props.value === "number" ? props.value : Number(props.value);
                if (!Number.isFinite(v)) return null;
                // Always label on the right of the bar's right edge: for a drop that is
                // the zero line, which keeps labels clear of the metric names.
                const right = Math.max(x, x + w);
                return (
                  <text
                    x={right + 6}
                    y={y + h / 2}
                    dominantBaseline="central"
                    textAnchor="start"
                    style={{ fill: "var(--ink-2)", fontSize: 11, fontVariantNumeric: "tabular-nums" }}
                  >
                    {fmtSigned(v)}
                  </text>
                );
              }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
