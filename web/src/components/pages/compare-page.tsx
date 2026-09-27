"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeftRight, GitCompareArrows, TriangleAlert } from "lucide-react";
import { MetricDeltaChart, type MetricDeltaRow } from "@/components/charts/delta-chart";
import { CaseMovement, TopMovers } from "@/components/compare/case-movers";
import { DeltaTable } from "@/components/compare/delta-table";
import { ExperimentPicker } from "@/components/compare/experiment-picker";
import { GatePanel } from "@/components/compare/gate-panel";
import { DemoBanner, DemoMaybe } from "@/components/common/demo";
import { Kpi, KpiStrip } from "@/components/common/kpi";
import { PageHeader, Panel } from "@/components/common/layout";
import { EmptyState, ErrorState, InlineLoading, NoExperiments, PageSkeleton } from "@/components/common/states";
import { DeltaText } from "@/components/common/verdict";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { api } from "@/lib/api";
import { fmtDateTime, fmtInt, fmtSigned, fmtSignedCost, fmtSignedMs, fmtSignedPp } from "@/lib/format";
import type { Comparison, ExperimentRef } from "@/lib/types";
import { urls } from "@/lib/urls";

export function ComparePage() {
  const params = useSearchParams();
  const router = useRouter();
  const baseline = params.get("baseline");
  const candidate = params.get("candidate");

  const list = useApi("experiments", () => api.experiments({ includeDemo: true, limit: 500 }));
  const experiments = useMemo(
    () => [...(list.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [list.data],
  );

  // Arriving with only a candidate (e.g. "Compare with…"): default the baseline to
  // the previous run on the same dataset.
  useEffect(() => {
    if (baseline || !candidate || experiments.length === 0) return;
    const cand = experiments.find((e) => e.id === candidate);
    if (!cand) return;
    const prev = experiments.find(
      (e) => e.id !== cand.id && e.dataset_name === cand.dataset_name && e.created_at < cand.created_at,
    );
    if (prev) router.replace(urls.compare(prev.id, cand.id), { scroll: false });
  }, [baseline, candidate, experiments, router]);

  const ready = Boolean(baseline && candidate && baseline !== candidate);
  const cmp = useApi(ready ? `compare:${baseline}:${candidate}` : null, () => api.compare(baseline!, candidate!));

  const setPair = (b: string | null, c: string | null) => router.replace(urls.compare(b, c), { scroll: false });

  const metricNames = useMemo(() => {
    const out: Record<string, string> = {};
    for (const e of experiments) for (const m of Object.values(e.summary.metrics)) out[m.metric] = m.display_name;
    return out;
  }, [experiments]);

  const header = (
    <PageHeader
      title="Compare experiments"
      description="Pick a baseline and a candidate. Green means better, red means worse; for cost, latency and escalation, lower is better."
    />
  );

  if (list.error)
    return (
      <>
        {header}
        <ErrorState error={list.error} onRetry={list.reload} />
      </>
    );
  if (!list.data) return <PageSkeleton kpis={4} panels={2} />;
  if (experiments.length === 0)
    return (
      <>
        {header}
        <NoExperiments />
      </>
    );

  return (
    <>
      {header}
      <Panel className="mb-6" bodyClassName="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <ExperimentPicker
            id="pick-baseline"
            label="Baseline"
            value={baseline}
            onChange={(id) => setPair(id, candidate)}
            experiments={experiments}
            exclude={candidate}
          />
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9 self-center sm:self-end"
            onClick={() => setPair(candidate, baseline)}
            disabled={!baseline && !candidate}
            aria-label="Swap baseline and candidate"
            title="Swap baseline and candidate"
          >
            <ArrowLeftRight aria-hidden />
          </Button>
          <ExperimentPicker
            id="pick-candidate"
            label="Candidate"
            value={candidate}
            onChange={(id) => setPair(baseline, id)}
            experiments={experiments}
            exclude={baseline}
          />
        </div>
      </Panel>

      {!ready ? (
        <EmptyState icon={<GitCompareArrows className="size-4.5" aria-hidden />} title={baseline && baseline === candidate ? "Pick two different experiments" : "Choose two experiments"}>
          <p>
            The baseline is the reference run, usually the older one. The candidate is the change you want to evaluate. You can
            also select two rows on the{" "}
            <Link href={urls.experiments()} className="font-medium text-ink underline underline-offset-2">
              experiments page
            </Link>
            .
          </p>
        </EmptyState>
      ) : cmp.error ? (
        <ErrorState error={cmp.error} onRetry={cmp.reload} />
      ) : !cmp.data ? (
        <Panel>
          <InlineLoading rows={8} />
        </Panel>
      ) : (
        <ComparisonView cmp={cmp.data} metricNames={metricNames} />
      )}
    </>
  );
}

function RefCard({ label, r }: { label: string; r: ExperimentRef }) {
  return (
    <div className="min-w-0">
      <div className="text-2xs text-ink-3">{label}</div>
      <div className="flex items-center gap-2">
        <Link href={urls.experiment(r.id)} className="truncate text-[0.9375rem] font-semibold text-ink hover:underline">
          {r.name}
        </Link>
        <DemoMaybe isDemo={r.is_demo} />
      </div>
      <div className="truncate text-xs text-ink-3">
        {r.dataset_name ?? "no dataset"}, {fmtDateTime(r.created_at)}
      </div>
    </div>
  );
}

function ComparisonView({ cmp, metricNames }: { cmp: Comparison; metricNames: Record<string, string> }) {
  const rows: MetricDeltaRow[] = Object.entries(cmp.metrics)
    .filter(([, d]) => d.delta !== null)
    .map(([m, d]) => ({ metric: m, label: metricNames[m] ?? m, baseline: d.baseline, candidate: d.candidate, delta: d.delta as number }))
    .sort((a, b) => a.delta - b.delta);
  const anyDemo = cmp.baseline.is_demo || cmp.candidate.is_demo;

  return (
    <>
      {anyDemo && <DemoBanner variant={cmp.baseline.is_demo && cmp.candidate.is_demo ? "global" : "mixed"} />}
      {!cmp.dataset_match && (
        <div role="note" className="mb-6 flex items-start gap-3 rounded-xl border border-hairline-strong bg-surface px-4 py-3 text-[0.8125rem] text-ink-2">
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn-ink" aria-hidden />
          <p>
            These experiments ran on different datasets or dataset versions. Aggregate deltas compare different case sets; case
            deltas only cover the {fmtInt(cmp.cases.matched)} case ids found in both.
          </p>
        </div>
      )}

      <div className="mb-6 grid items-center gap-4 rounded-xl border border-hairline bg-surface px-4 py-3.5 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
        <RefCard label="Baseline" r={cmp.baseline} />
        <ArrowLeftRight className="hidden size-4 text-ink-3 sm:block" aria-hidden />
        <RefCard label="Candidate" r={cmp.candidate} />
      </div>

      <KpiStrip className="mb-6 lg:grid-cols-4">
        <Kpi
          label="Overall score"
          value={
            <DeltaText delta={cmp.overall_score.delta} better="higher" epsilon={0.0005}>
              {fmtSigned(cmp.overall_score.delta)}
            </DeltaText>
          }
          sub="candidate minus baseline"
        />
        <Kpi
          label="Pass rate"
          value={
            <DeltaText delta={cmp.pass_rate.delta} better="higher" epsilon={0.0005}>
              {fmtSignedPp(cmp.pass_rate.delta)}
            </DeltaText>
          }
          sub={`${fmtInt(cmp.cases.regressed)} cases regressed, ${fmtInt(cmp.cases.improved)} improved`}
        />
        <Kpi
          label="Cost per case"
          value={
            <DeltaText delta={cmp.cost_per_case_usd.delta} better="lower" epsilon={1e-8}>
              {fmtSignedCost(cmp.cost_per_case_usd.delta)}
            </DeltaText>
          }
          sub="lower is better"
        />
        <Kpi
          label="Latency p95"
          value={
            <DeltaText delta={cmp.latency_p95_ms.delta} better="lower" epsilon={0.5}>
              {fmtSignedMs(cmp.latency_p95_ms.delta)}
            </DeltaText>
          }
          sub="lower is better"
        />
      </KpiStrip>

      <div className="grid items-start gap-6 xl:grid-cols-5">
        <Panel className="xl:col-span-3" title="All deltas">
          <DeltaTable cmp={cmp} metricNames={metricNames} />
        </Panel>
        <div className="grid gap-6 xl:col-span-2">
          <Panel title="Metric score change" description="Mean score, candidate minus baseline. Sorted worst first." bodyClassName="px-2 pb-3">
            {rows.length ? <MetricDeltaChart rows={rows} /> : <p className="px-2 pb-2 text-xs text-ink-3">No metrics in common.</p>}
          </Panel>
          <Panel title="Case movement" description="Matched cases by change in overall score." bodyClassName="px-4 pb-4">
            <CaseMovement cmp={cmp} />
          </Panel>
        </div>
      </div>

      <div className="mt-6">
        <TopMovers cmp={cmp} />
      </div>

      <div className="mt-6">
        <GatePanel key={`${cmp.baseline.id}:${cmp.candidate.id}`} cmp={cmp} metricNames={metricNames} />
      </div>
    </>
  );
}
