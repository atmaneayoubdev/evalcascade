"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { EyeOff, GitCompareArrows, Search, X } from "lucide-react";
import { cn } from "cn";
import { compareValues, DemoToggle, SortableHead, type SortDir } from "@/components/common/controls";
import { DemoBanner, DemoMaybe } from "@/components/common/demo";
import { PageHeader, Panel } from "@/components/common/layout";
import { EmptyState, ErrorState, NoExperiments, PageSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { demoPreference, resolveDemo, useStored } from "@/hooks/use-stored";
import { api } from "@/lib/api";
import { fmtCost, fmtDate, fmtInt, fmtMs, fmtPct, fmtRelativeTime, fmtScore } from "@/lib/format";
import type { ExperimentListItem } from "@/lib/types";
import { urls } from "@/lib/urls";

type Key = "name" | "dataset" | "created" | "overall" | "pass" | "cases" | "cost" | "p50" | "jev" | "esc";

const VALUE: Record<Key, (e: ExperimentListItem) => number | string | null> = {
  name: (e) => e.name.toLowerCase(),
  dataset: (e) => e.dataset_name?.toLowerCase() ?? null,
  created: (e) => e.created_at,
  overall: (e) => e.summary.overall_score,
  pass: (e) => e.summary.pass_rate,
  cases: (e) => e.summary.num_cases,
  cost: (e) => e.summary.cost_usd,
  p50: (e) => e.summary.latency_ms.p50,
  jev: (e) => e.summary.routing.jev_acceptance_rate,
  esc: (e) => e.summary.routing.escalation_rate,
};

export function ExperimentsPage() {
  const { data, error, loading, reload } = useApi("experiments", () => api.experiments({ includeDemo: true, limit: 500 }));
  const [pref, setPref] = useStored(demoPreference);
  const [sort, setSort] = useState<{ key: Key; dir: SortDir }>({ key: "created", dir: "desc" });
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const router = useRouter();

  const all = useMemo(() => data ?? [], [data]);
  const hasReal = all.some((e) => !e.is_demo);
  const hasDemo = all.some((e) => e.is_demo);
  const includeDemo = resolveDemo(pref, hasReal);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return all
      .filter((e) => includeDemo || !e.is_demo)
      .filter(
        (e) =>
          !q ||
          e.name.toLowerCase().includes(q) ||
          (e.dataset_name ?? "").toLowerCase().includes(q) ||
          e.tags.some((t) => t.toLowerCase().includes(q)),
      )
      .sort((a, b) => compareValues(VALUE[sort.key](a), VALUE[sort.key](b), sort.dir));
  }, [all, includeDemo, query, sort]);

  const visibleIds = new Set(rows.map((r) => r.id));
  const picked = selected.filter((id) => visibleIds.has(id));

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 2 ? s : [...s, id]));

  const compareSelected = () => {
    const [a, b] = picked.map((id) => all.find((e) => e.id === id)!).sort((x, y) => x.created_at.localeCompare(y.created_at));
    if (a && b) router.push(urls.compare(a.id, b.id));
  };

  const header = (
    <PageHeader
      title="Experiments"
      description="Each experiment is one run of a metric suite over a dataset. Select two to compare them."
      actions={hasDemo ? <DemoToggle checked={includeDemo} onCheckedChange={(v) => setPref(v ? "show" : "hide")} /> : undefined}
    />
  );

  if (error)
    return (
      <>
        {header}
        <ErrorState error={error} onRetry={reload} />
      </>
    );
  if (loading || !data) return <PageSkeleton kpis={0} panels={1} />;
  if (all.length === 0)
    return (
      <>
        {header}
        <NoExperiments />
      </>
    );

  const onlyDemoVisible = rows.length > 0 && rows.every((r) => r.is_demo);

  return (
    <>
      {header}
      {onlyDemoVisible && !hasReal && <DemoBanner />}
      {hasReal && includeDemo && hasDemo && <DemoBanner variant="mixed" />}

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="relative w-full max-w-72">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by name, dataset or tag"
              aria-label="Filter experiments"
              className="h-8 pl-8 text-[0.8125rem]"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2" aria-live="polite">
            <span className="text-xs text-ink-3">
              {picked.length === 0 && "Select two experiments to compare"}
              {picked.length === 1 && "Select one more to compare"}
              {picked.length === 2 && "Older run becomes the baseline"}
            </span>
            {picked.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => setSelected([])}>
                <X aria-hidden />
                Clear
              </Button>
            )}
            <Button size="sm" disabled={picked.length !== 2} onClick={compareSelected}>
              <GitCompareArrows aria-hidden />
              Compare selected
            </Button>
          </div>
        </div>

        {rows.length === 0 ? (
          !includeDemo && hasDemo && !query ? (
            <EmptyState
              className="rounded-none border-x-0 border-b-0"
              icon={<EyeOff className="size-4.5" aria-hidden />}
              title="Only demo experiments are recorded"
              actions={
                <Button variant="outline" size="sm" onClick={() => setPref("show")}>
                  Show demo data
                </Button>
              }
            >
              <p>Demo data is hidden, and there are no real experiments yet.</p>
            </EmptyState>
          ) : (
            <p className="border-t border-hairline px-4 py-10 text-center text-xs text-ink-3">No experiments match “{query}”.</p>
          )
        ) : (
          <Table className="min-w-[1080px]">
            <TableHeader>
              <TableRow>
                <TableHead className="w-10 pl-4">
                  <span className="sr-only">Select</span>
                </TableHead>
                <SortableHead label="Name" sortKey="name" sort={sort} onSort={setSort} defaultDir="asc" />
                <SortableHead label="Dataset" sortKey="dataset" sort={sort} onSort={setSort} defaultDir="asc" />
                <SortableHead label="Created" sortKey="created" sort={sort} onSort={setSort} />
                <SortableHead label="Overall" sortKey="overall" sort={sort} onSort={setSort} align="right" />
                <SortableHead label="Pass rate" sortKey="pass" sort={sort} onSort={setSort} align="right" />
                <SortableHead label="Cases" sortKey="cases" sort={sort} onSort={setSort} align="right" />
                <SortableHead label="Cost" sortKey="cost" sort={sort} onSort={setSort} align="right" />
                <SortableHead label="p50 latency" sortKey="p50" sort={sort} onSort={setSort} align="right" />
                <SortableHead label="Jev accepted" sortKey="jev" sort={sort} onSort={setSort} align="right" />
                <SortableHead label="Escalated" sortKey="esc" sort={sort} onSort={setSort} align="right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((e) => {
                const isSel = picked.includes(e.id);
                const disabled = !isSel && picked.length >= 2;
                return (
                  <TableRow key={e.id} data-state={isSel ? "selected" : undefined}>
                    <TableCell className="pl-4">
                      <Checkbox
                        checked={isSel}
                        disabled={disabled}
                        onCheckedChange={() => toggle(e.id)}
                        aria-label={`Select ${e.name} for comparison`}
                      />
                    </TableCell>
                    <TableCell className="max-w-[20rem]">
                      <div className="flex items-center gap-2">
                        <Link href={urls.experiment(e.id)} className="truncate font-medium text-ink hover:underline">
                          {e.name}
                        </Link>
                        <DemoMaybe isDemo={e.is_demo} />
                      </div>
                      {e.tags.length > 0 && (
                        <div className="mt-0.5 flex gap-1">
                          {e.tags.slice(0, 4).map((t) => (
                            <span key={t} className="rounded-[3px] bg-sunken px-1 text-2xs text-ink-3">
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-ink-2">{e.dataset_name ?? "—"}</TableCell>
                    <TableCell className="text-ink-2">
                      <span title={fmtDate(e.created_at)}>{fmtRelativeTime(e.created_at)}</span>
                    </TableCell>
                    <TableCell className="tabular text-right font-medium">{fmtScore(e.summary.overall_score)}</TableCell>
                    <TableCell className="tabular text-right">{fmtPct(e.summary.pass_rate)}</TableCell>
                    <TableCell className="tabular text-right">{fmtInt(e.summary.num_cases)}</TableCell>
                    <TableCell className={cn("tabular text-right", !e.summary.cost_complete && "text-warn-ink")}>
                      {fmtCost(e.summary.cost_usd)}
                      {!e.summary.cost_complete && <span title="Some evaluator calls had unknown cost">*</span>}
                    </TableCell>
                    <TableCell className="tabular text-right">{fmtMs(e.summary.latency_ms.p50)}</TableCell>
                    <TableCell className="tabular text-right">{fmtPct(e.summary.routing.jev_acceptance_rate)}</TableCell>
                    <TableCell className="tabular text-right">{fmtPct(e.summary.routing.escalation_rate)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Panel>
      <p className="mt-2 text-xs text-ink-3">
        {rows.length} of {all.length} experiments shown.
        {all.some((e) => !e.summary.cost_complete) && " * Cost incomplete: some evaluator calls reported no price."}
      </p>
    </>
  );
}
