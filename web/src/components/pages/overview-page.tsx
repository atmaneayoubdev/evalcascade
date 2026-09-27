"use client";

import Link from "next/link";
import { CircleCheck, EyeOff, TriangleAlert } from "lucide-react";
import { RoutingCascade } from "@/components/charts/cascade";
import { TrendChart } from "@/components/charts/trend-chart";
import { DemoToggle } from "@/components/common/controls";
import { DemoBanner, DemoMaybe } from "@/components/common/demo";
import { Kpi, KpiStrip } from "@/components/common/kpi";
import { PageHeader, Panel } from "@/components/common/layout";
import { RouteBar } from "@/components/common/route";
import { EmptyState, ErrorState, NoExperiments, PageSkeleton } from "@/components/common/states";
import { DeltaText } from "@/components/common/verdict";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { demoPreference, useStored } from "@/hooks/use-stored";
import { api } from "@/lib/api";
import { fmtCost, fmtInt, fmtMs, fmtPct, fmtRelativeTime, fmtScore, fmtSigned } from "@/lib/format";
import type { ExperimentListItem, Overview, RegressionIndicator } from "@/lib/types";
import { routingCounts } from "@/lib/route-meta";
import { urls } from "@/lib/urls";

function useOverview() {
  const [pref, setPref] = useStored(demoPreference);
  const explicit = pref === "show" ? true : pref === "hide" ? false : null;
  // "auto": ask for everything first; if real data exists, re-ask without demo so
  // synthetic numbers never blend into real averages.
  const first = useApi(`overview:${explicit ?? "auto"}`, () => api.overview(explicit ?? true));
  const needsRealOnly = explicit === null && first.data?.has_real_data === true && first.data.has_demo_data;
  const second = useApi(needsRealOnly ? "overview:real-only" : null, () => api.overview(false));
  const state = needsRealOnly ? second : first;
  const includeDemo = explicit ?? !first.data?.has_real_data;
  return { ...state, reload: () => (needsRealOnly ? second.reload() : first.reload()), includeDemo, setPref };
}

export function OverviewPage() {
  const { data, error, loading, reload, includeDemo, setPref } = useOverview();

  const header = (o?: Overview) => (
    <PageHeader
      title="Overview"
      description="Quality, cost and routing across recorded experiments."
      actions={
        o?.has_demo_data ? <DemoToggle checked={includeDemo} onCheckedChange={(v) => setPref(v ? "show" : "hide")} /> : undefined
      }
    />
  );

  if (error) {
    return (
      <>
        {header()}
        <ErrorState error={error} onRetry={reload} />
      </>
    );
  }
  if (loading || !data) return <PageSkeleton kpis={8} panels={2} />;

  if (data.totals.experiments === 0) {
    return (
      <>
        {header(data)}
        {data.has_demo_data && !includeDemo ? (
          <EmptyState
            icon={<EyeOff className="size-4.5" aria-hidden />}
            title="Only demo experiments are recorded"
            actions={
              <Button variant="outline" size="sm" onClick={() => setPref("show")}>
                Show demo data
              </Button>
            }
          >
            <p>Demo data is hidden. Show it, or record a real run with evalcascade run.</p>
          </EmptyState>
        ) : (
          <NoExperiments />
        )}
      </>
    );
  }

  const nameById = new Map<string, string>();
  for (const e of data.recent) nameById.set(e.id, e.name);
  for (const t of data.trend) nameById.set(t.id, t.name);

  return (
    <>
      {header(data)}
      {!data.has_real_data ? <DemoBanner /> : includeDemo && data.has_demo_data ? <DemoBanner variant="mixed" /> : null}
      <OverviewKpis o={data} />

      <div className="mt-6 grid gap-6 xl:grid-cols-5">
        <Panel
          className="xl:col-span-3"
          title="Where judgments were decided"
          description="Every metric evaluation, by the cheapest judge that could settle it."
          bodyClassName="px-4 pb-4"
        >
          <RoutingCascade counts={data.routing} />
        </Panel>
        <Panel
          className="xl:col-span-2"
          title="Regression watch"
          description="Each experiment against the previous run on the same dataset."
        >
          <RegressionList items={data.regressions} names={nameById} />
        </Panel>
      </div>

      <Panel className="mt-6" title="Over time" description="One point per experiment, oldest first. Click a point to open it." bodyClassName="px-4 pb-4">
        {data.trend.length > 0 ? <TrendChart points={data.trend} /> : <p className="py-8 text-center text-xs text-ink-3">No trend yet.</p>}
      </Panel>

      <Panel
        className="mt-6"
        title="Recent experiments"
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link href={urls.experiments()}>All experiments</Link>
          </Button>
        }
      >
        <RecentTable items={data.recent} />
      </Panel>
    </>
  );
}

function OverviewKpis({ o }: { o: Overview }) {
  const costIncomplete = o.recent.some((e) => !e.summary.cost_complete);
  const latest = o.recent[0];
  return (
    <KpiStrip className="2xl:grid-cols-8">
      <Kpi
        label="Overall quality"
        value={fmtScore(o.averages.overall_score)}
        sub={`mean of ${fmtInt(o.totals.experiments)} experiments`}
        hint="Mean overall score (0–1) across experiments. Each case's overall score is the weighted mean of its metric scores."
      />
      <Kpi label="Pass rate" value={fmtPct(o.averages.pass_rate)} sub="cases passing every metric" />
      <Kpi label="Evaluations" value={fmtInt(o.totals.evaluations)} sub={`${fmtInt(o.totals.cases)} cases`} hint="Metric evaluations: one per metric per case." />
      <Kpi
        label="Jev acceptance"
        swatch="var(--route-jev)"
        value={fmtPct(o.averages.jev_acceptance_rate)}
        sub="kept without escalation"
        hint="Share of Jev judgments confident enough (at or above escalate_below) to be final."
      />
      <Kpi
        label="LLM escalation"
        swatch="var(--route-esc)"
        value={fmtPct(o.averages.escalation_rate)}
        sub="of Jev attempts"
        hint="Share of Jev attempts handed to the LLM judge because confidence was low or the call failed."
      />
      <Kpi
        label="Latency p50"
        value={fmtMs(o.averages.latency_p50_ms)}
        sub={o.averages.latency_mean_ms !== null ? `mean ${fmtMs(o.averages.latency_mean_ms)}` : "per case"}
        hint="Wall-clock time to evaluate one case, all metrics included. Median and mean, averaged across experiments."
      />
      <Kpi
        label="Evaluation cost"
        value={fmtCost(o.totals.cost_usd)}
        sub={costIncomplete ? "some costs unknown" : o.totals.evaluations > 0 ? `${fmtCost(o.totals.cost_usd / o.totals.evaluations)} per evaluation` : undefined}
        hint="Total judge spend in USD. LLM costs may be estimated from list prices when the provider doesn't report them."
      />
      <Kpi label="Experiments" value={fmtInt(o.totals.experiments)} sub={latest ? `latest ${fmtRelativeTime(latest.created_at)}` : undefined} />
    </KpiStrip>
  );
}

function RegressionList({ items, names }: { items: RegressionIndicator[]; names: Map<string, string> }) {
  if (items.length === 0) {
    return (
      <p className="px-4 pb-5 text-xs text-ink-3">
        Needs at least two experiments on the same dataset. Run the same dataset again to see how it moved.
      </p>
    );
  }
  return (
    <ul className="divide-y divide-hairline border-t border-hairline">
      {items.slice(0, 8).map((r) => (
        <li key={`${r.baseline_id}-${r.candidate_id}`}>
          <Link
            href={urls.compare(r.baseline_id, r.candidate_id)}
            className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 px-4 py-2.5 transition-colors hover:bg-sunken/60"
          >
            {r.regressed ? (
              <TriangleAlert className="size-4 text-bad-ink" aria-label="Regressed" />
            ) : (
              <CircleCheck className="size-4 text-good-ink" aria-label="No regression" />
            )}
            <span className="min-w-0">
              <span className="flex items-center gap-2">
                <span className="truncate text-[0.8125rem] font-medium text-ink">{r.name}</span>
                <DemoMaybe isDemo={r.is_demo} />
              </span>
              <span className="block truncate text-2xs text-ink-3">
                vs {names.get(r.baseline_id) ?? r.baseline_id}
              </span>
            </span>
            <span className="text-right text-xs">
              <DeltaText delta={r.delta_overall} better="higher" epsilon={0.0005}>
                {fmtSigned(r.delta_overall)}
              </DeltaText>
              <span className={`block text-2xs ${r.regressed ? "text-bad-ink" : "text-ink-3"}`}>
                {r.regressed ? "Regressed" : "No regression"}
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RecentTable({ items }: { items: ExperimentListItem[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Experiment</TableHead>
          <TableHead>Dataset</TableHead>
          <TableHead>Created</TableHead>
          <TableHead className="text-right">Overall</TableHead>
          <TableHead className="text-right">Pass rate</TableHead>
          <TableHead className="w-40">Routing</TableHead>
          <TableHead className="text-right">Cost</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((e) => (
          <TableRow key={e.id}>
            <TableCell className="max-w-[22rem]">
              <span className="flex items-center gap-2">
                <Link href={urls.experiment(e.id)} className="truncate font-medium text-ink hover:underline">
                  {e.name}
                </Link>
                <DemoMaybe isDemo={e.is_demo} />
              </span>
            </TableCell>
            <TableCell className="text-ink-2">{e.dataset_name ?? "—"}</TableCell>
            <TableCell className="text-ink-2">{fmtRelativeTime(e.created_at)}</TableCell>
            <TableCell className="tabular text-right font-medium">{fmtScore(e.summary.overall_score)}</TableCell>
            <TableCell className="tabular text-right">{fmtPct(e.summary.pass_rate)}</TableCell>
            <TableCell>
              <RouteBar counts={routingCounts(e.summary.routing)} height={6} />
            </TableCell>
            <TableCell className="tabular text-right">{fmtCost(e.summary.cost_usd)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
