import { Fragment } from "react";
import { DeltaText, type Better } from "@/components/common/verdict";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  fmtCost,
  fmtMs,
  fmtPct,
  fmtRelative,
  fmtScore,
  fmtSigned,
  fmtSignedCost,
  fmtSignedMs,
  fmtSignedPp,
} from "@/lib/format";
import type { Comparison, Delta } from "@/lib/types";

interface Row {
  label: string;
  sub?: string;
  d: Delta;
  better: Better;
  value: (v: number | null) => string;
  change: (v: number | null) => string;
  epsilon: number;
}

export function DeltaTable({ cmp, metricNames }: { cmp: Comparison; metricNames: Record<string, string> }) {
  const score = { value: (v: number | null) => fmtScore(v), change: (v: number | null) => fmtSigned(v), epsilon: 0.0005 };
  const rate = { value: (v: number | null) => fmtPct(v), change: (v: number | null) => fmtSignedPp(v), epsilon: 0.0005 };
  const groups: { title: string; rows: Row[] }[] = [
    {
      title: "Quality",
      rows: [
        { label: "Overall score", d: cmp.overall_score, better: "higher", ...score },
        { label: "Pass rate", d: cmp.pass_rate, better: "higher", ...rate },
      ],
    },
    {
      title: "Metrics (mean score)",
      rows: Object.entries(cmp.metrics).map(([m, d]) => ({
        label: metricNames[m] ?? m,
        sub: m,
        d,
        better: "higher" as const,
        ...score,
      })),
    },
    {
      title: "Cost and latency",
      rows: [
        { label: "Total cost", d: cmp.cost_usd, better: "lower", value: fmtCost, change: fmtSignedCost, epsilon: 1e-7 },
        { label: "Cost per case", d: cmp.cost_per_case_usd, better: "lower", value: fmtCost, change: fmtSignedCost, epsilon: 1e-8 },
        { label: "Latency p50", d: cmp.latency_p50_ms, better: "lower", value: fmtMs, change: fmtSignedMs, epsilon: 0.5 },
        { label: "Latency p95", d: cmp.latency_p95_ms, better: "lower", value: fmtMs, change: fmtSignedMs, epsilon: 0.5 },
      ],
    },
    {
      title: "Routing",
      rows: [
        { label: "Jev acceptance", d: cmp.jev_acceptance_rate, better: "higher", ...rate },
        { label: "Escalation rate", d: cmp.escalation_rate, better: "lower", ...rate },
      ],
    },
  ];

  return (
    <Table className="min-w-[560px]">
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">Measure</TableHead>
          <TableHead className="text-right">Baseline</TableHead>
          <TableHead className="text-right">Candidate</TableHead>
          <TableHead className="text-right">Change</TableHead>
          <TableHead className="pr-4 text-right">Relative</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {groups.map((g) =>
          g.rows.length === 0 ? null : (
            <Fragment key={g.title}>
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={5} className="bg-sunken/50 pt-3 pb-1.5 pl-4 text-2xs font-medium text-ink-3">
                  {g.title}
                </TableCell>
              </TableRow>
              {g.rows.map((r) => (
                <TableRow key={`${g.title}-${r.label}`}>
                  <TableCell className="pl-4">
                    <span className="text-ink">{r.label}</span>
                    {r.sub && r.sub !== r.label && <span className="ml-2 font-mono text-2xs text-ink-3">{r.sub}</span>}
                  </TableCell>
                  <TableCell className="tabular text-right text-ink-2">{r.value(r.d.baseline)}</TableCell>
                  <TableCell className="tabular text-right text-ink">{r.value(r.d.candidate)}</TableCell>
                  <TableCell className="text-right">
                    <DeltaText delta={r.d.delta} better={r.better} epsilon={r.epsilon}>
                      {r.change(r.d.delta)}
                    </DeltaText>
                  </TableCell>
                  <TableCell className="tabular pr-4 text-right text-xs text-ink-3">{fmtRelative(r.d.relative)}</TableCell>
                </TableRow>
              ))}
            </Fragment>
          ),
        )}
      </TableBody>
    </Table>
  );
}
