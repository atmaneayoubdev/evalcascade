"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight, ListTree } from "lucide-react";
import { cn } from "cn";
import { Segmented } from "@/components/common/controls";
import { RouteDot, RouteLegend } from "@/components/common/route";
import { ErrorState, InlineLoading } from "@/components/common/states";
import { PassBadge } from "@/components/common/verdict";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useApi } from "@/hooks/use-api";
import { api, type CaseFilter } from "@/lib/api";
import { fmtCost, fmtInt, fmtMs, fmtScore } from "@/lib/format";
import { ROUTE_META } from "@/lib/route-meta";
import { urls } from "@/lib/urls";

export const PAGE_SIZE = 20;

const FILTERS: { value: CaseFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "escalated", label: "Escalated" },
];

export function CasesTable({
  experimentId,
  metricOrder,
  metricNames,
  filter,
  page,
  onChange,
}: {
  experimentId: string;
  metricOrder: string[];
  metricNames: Record<string, string>;
  filter: CaseFilter;
  page: number;
  onChange: (next: { filter: CaseFilter; page: number }) => void;
}) {
  const offset = page * PAGE_SIZE;
  const { data, error, loading, previous, reload } = useApi(`cases:${experimentId}:${filter}:${offset}`, () =>
    api.cases(experimentId, { limit: PAGE_SIZE, offset, filter }),
  );
  const shown = data ?? (loading ? previous : undefined);
  const total = shown?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const columns = shown?.items.length
    ? [...metricOrder, ...Object.keys(shown.items[0].metrics).filter((m) => !metricOrder.includes(m))]
    : metricOrder;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-3">
        <Segmented
          label="Filter cases"
          value={filter}
          onChange={(f) => onChange({ filter: f, page: 0 })}
          options={FILTERS}
        />
        <RouteLegend />
      </div>

      {error ? (
        <ErrorState error={error} onRetry={reload} className="m-4 mt-0" />
      ) : !shown ? (
        <InlineLoading rows={8} />
      ) : shown.items.length === 0 ? (
        <p className="border-t border-hairline px-4 py-10 text-center text-xs text-ink-3">
          {filter === "all" ? "This experiment has no cases." : `No ${filter} cases.`}
        </p>
      ) : (
        <div className={cn("transition-opacity", loading && "opacity-60")} aria-busy={loading}>
          <Table className="min-w-[960px]">
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Case</TableHead>
                <TableHead>Input</TableHead>
                <TableHead className="text-right">Overall</TableHead>
                <TableHead>Result</TableHead>
                {columns.map((m) => (
                  <TableHead key={m} className="max-w-[6.5rem] text-right leading-tight whitespace-normal">
                    {metricNames[m] ?? m}
                  </TableHead>
                ))}
                <TableHead className="text-right">Esc.</TableHead>
                <TableHead className="text-right">Latency</TableHead>
                <TableHead className="pr-4 text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.items.map((c) => {
                const href = urls.caseView(experimentId, c.case_id);
                return (
                  <TableRow key={c.case_id} className="group">
                    <TableCell className="pl-4">
                      <Link href={href} className="inline-flex items-center gap-1.5 font-mono text-xs font-medium text-ink hover:underline">
                        {c.case_id}
                        {c.has_trace && <ListTree className="size-3.5 text-ink-3" aria-label="Has agent trace" />}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-[18rem]">
                      <Link href={href} className="block truncate text-ink-2 group-hover:text-ink" title={c.input_preview}>
                        {c.input_preview || <span className="text-ink-3">(no input)</span>}
                      </Link>
                    </TableCell>
                    <TableCell className="tabular text-right font-medium">{fmtScore(c.overall_score)}</TableCell>
                    <TableCell>
                      <PassBadge passed={c.passed} />
                    </TableCell>
                    {columns.map((m) => {
                      const r = c.metrics[m];
                      if (!r) return <TableCell key={m} className="text-right text-ink-3">—</TableCell>;
                      return (
                        <TableCell key={m} className="text-right">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span tabIndex={0} className="tabular inline-flex items-center justify-end gap-1.5">
                                <RouteDot route={r.route} />
                                {r.status !== "ok" ? (
                                  <span className="text-xs text-ink-3">{r.status}</span>
                                ) : (
                                  <span className={cn(r.passed === false ? "font-medium text-bad-ink" : "text-ink")}>
                                    {fmtScore(r.score, 2)}
                                  </span>
                                )}
                              </span>
                            </TooltipTrigger>
                            <TooltipContent>
                              {metricNames[m] ?? m}: {r.status === "ok" ? `${fmtScore(r.score)} (${r.passed ? "pass" : "fail"})` : r.status}
                              {", "}
                              {ROUTE_META[r.route].label}
                            </TooltipContent>
                          </Tooltip>
                        </TableCell>
                      );
                    })}
                    <TableCell className={cn("tabular text-right", c.escalations > 0 ? "text-route-esc-ink font-medium" : "text-ink-3")}>
                      {fmtInt(c.escalations)}
                    </TableCell>
                    <TableCell className="tabular text-right">{fmtMs(c.latency_ms)}</TableCell>
                    <TableCell className="tabular pr-4 text-right">{fmtCost(c.cost_usd)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {shown && total > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline px-4 py-2.5 text-xs text-ink-3">
          <span className="tabular">
            {fmtInt(offset + 1)}–{fmtInt(Math.min(total, offset + PAGE_SIZE))} of {fmtInt(total)} cases
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => onChange({ filter, page: page - 1 })}
              aria-label="Previous page"
            >
              <ChevronLeft aria-hidden />
              Previous
            </Button>
            <span className="tabular px-2">
              Page {page + 1} of {pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={page + 1 >= pages}
              onClick={() => onChange({ filter, page: page + 1 })}
              aria-label="Next page"
            >
              Next
              <ChevronRight aria-hidden />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
