import { MiniHistogram } from "@/components/charts/histogram";
import { RouteBar } from "@/components/common/route";
import { ScoreBar } from "@/components/common/verdict";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CATEGORY_LABEL, fmtCost, fmtInt, fmtMs, fmtPct, fmtScore } from "@/lib/format";
import type { MetricSummary } from "@/lib/types";

/** One row per metric: score against threshold, distribution, routing and spend. */
export function MetricMatrix({
  metrics,
  thresholds,
}: {
  metrics: MetricSummary[];
  thresholds: Record<string, number | null>;
}) {
  return (
    <Table className="min-w-[1040px]">
      <TableHeader>
        <TableRow>
          <TableHead className="pl-4">Metric</TableHead>
          <TableHead className="w-[15rem]">Mean score vs threshold</TableHead>
          <TableHead className="text-right">Pass rate</TableHead>
          <TableHead className="w-[9.5rem]">Distribution</TableHead>
          <TableHead className="w-[12rem]">Routing</TableHead>
          <TableHead className="text-right">Escalated</TableHead>
          <TableHead className="text-right">Mean latency</TableHead>
          <TableHead className="pr-4 text-right">Cost</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {metrics.map((m) => {
          const thr = thresholds[m.metric] ?? null;
          const below = m.mean !== null && thr !== null && m.mean < thr;
          return (
            <TableRow key={m.metric}>
              <TableCell className="pl-4">
                <div className="font-medium text-ink">{m.display_name}</div>
                <div className="text-2xs text-ink-3">
                  <span className="font-mono">{m.metric}</span>
                  <span className="ml-2">{CATEGORY_LABEL[m.category]}</span>
                </div>
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-3">
                  <ScoreBar value={m.mean} threshold={thr} tone={m.mean === null ? "neutral" : below ? "bad" : "good"} className="w-28" />
                  <span className="tabular text-right">
                    <span className="font-medium text-ink">{fmtScore(m.mean)}</span>
                    {thr !== null && <span className="block text-2xs text-ink-3">threshold {thr.toFixed(2)}</span>}
                  </span>
                </div>
              </TableCell>
              <TableCell className="tabular text-right">
                <span className="font-medium">{fmtPct(m.pass_rate)}</span>
                <span className="block text-2xs text-ink-3">
                  {fmtInt(m.count)} judged
                  {m.skipped > 0 && `, ${m.skipped} skipped`}
                  {m.errors > 0 && `, ${m.errors} errors`}
                </span>
              </TableCell>
              <TableCell>
                <MiniHistogram bins={m.histogram} threshold={thr} className="w-32" />
              </TableCell>
              <TableCell>
                <RouteBar counts={m.routes} height={7} />
              </TableCell>
              <TableCell className="tabular text-right">{m.escalation_rate === null ? "n/a" : fmtPct(m.escalation_rate)}</TableCell>
              <TableCell className="tabular text-right">{fmtMs(m.mean_latency_ms)}</TableCell>
              <TableCell className="tabular pr-4 text-right">{fmtCost(m.cost_usd)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
