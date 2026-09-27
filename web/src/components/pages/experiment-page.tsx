"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Calendar, Database, GitCompareArrows, Hash, Tag } from "lucide-react";
import { RoutingCascade } from "@/components/charts/cascade";
import { DemoBanner, DemoMaybe } from "@/components/common/demo";
import { Kpi, KpiStrip } from "@/components/common/kpi";
import { PageHeader, Panel } from "@/components/common/layout";
import { ErrorState, NotFoundState, PageSkeleton } from "@/components/common/states";
import { CasesTable } from "@/components/experiment/cases-table";
import { ConfigPanel } from "@/components/experiment/config-panel";
import { MetricMatrix } from "@/components/experiment/metric-matrix";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { recentExperiment } from "@/hooks/use-stored";
import { api, type CaseFilter } from "@/lib/api";
import { fmtCost, fmtDateTime, fmtInt, fmtMs, fmtPct, fmtScore } from "@/lib/format";
import { routingCounts } from "@/lib/route-meta";
import type { Experiment, MetricInfo } from "@/lib/types";
import { urls } from "@/lib/urls";

const FILTERS: CaseFilter[] = ["all", "passed", "failed", "escalated"];

export function thresholdsFor(e: Experiment, catalog: MetricInfo[] | undefined): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const [name, summary] of Object.entries(e.summary.metrics)) {
    // Prefer the threshold the run actually used; fall back to configured params, then the catalog default.
    if (typeof summary.threshold === "number") {
      out[name] = summary.threshold;
      continue;
    }
    const cfg = e.metrics.find((m) => m.name === name)?.params.threshold;
    out[name] = typeof cfg === "number" ? cfg : (catalog?.find((m) => m.name === name)?.default_threshold ?? null);
  }
  return out;
}

export function ExperimentPage() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const rawFilter = params.get("filter") as CaseFilter | null;
  const filter: CaseFilter = rawFilter && FILTERS.includes(rawFilter) ? rawFilter : "all";
  const page = Math.max(0, Number.parseInt(params.get("page") ?? "1", 10) - 1 || 0);

  const exp = useApi(id ? `experiment:${id}` : null, () => api.experiment(id!));
  const catalog = useApi("metrics", () => api.metrics());
  const e = exp.data;

  useEffect(() => {
    if (!e) return;
    recentExperiment.set(JSON.stringify({ id: e.id, name: e.name }));
    document.title = `${e.name} | EvalCascade`;
  }, [e]);

  const metricOrder = useMemo(() => {
    if (!e) return [];
    const configured = e.metrics.map((m) => m.name).filter((n) => n in e.summary.metrics);
    return [...configured, ...Object.keys(e.summary.metrics).filter((n) => !configured.includes(n))];
  }, [e]);

  if (!id) {
    return (
      <>
        <PageHeader title="Experiment" crumbs={[{ label: "Experiments", href: urls.experiments() }]} />
        <NotFoundState what="This experiment" detail="No experiment id in the link. Pick one from the experiments list." />
      </>
    );
  }
  if (exp.error) {
    return (
      <>
        <PageHeader title="Experiment" crumbs={[{ label: "Experiments", href: urls.experiments() }]} />
        {exp.error.kind === "not_found" ? (
          <NotFoundState what="This experiment" detail={`No experiment with id “${id}”.`} />
        ) : (
          <ErrorState error={exp.error} onRetry={exp.reload} />
        )}
      </>
    );
  }
  if (!e) return <PageSkeleton kpis={8} panels={3} />;

  const s = e.summary;
  const thresholds = thresholdsFor(e, catalog.data);
  const metricNames = Object.fromEntries(Object.values(s.metrics).map((m) => [m.metric, m.display_name]));

  const setCases = (next: { filter: CaseFilter; page: number }) => {
    const url = urls.experiment(e.id, {
      filter: next.filter === "all" ? undefined : next.filter,
      page: next.page > 0 ? next.page + 1 : undefined,
    });
    router.replace(url, { scroll: false });
  };

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Experiments", href: urls.experiments() }, { label: e.name }]}
        title={e.name}
        badge={<DemoMaybe isDemo={e.is_demo} />}
        meta={
          <>
            <span className="inline-flex items-center gap-1.5">
              <Database className="size-3.5" aria-hidden />
              {e.dataset_name ?? e.dataset.name ?? "unnamed dataset"}
              <span className="text-ink-3">({fmtInt(e.dataset.size)} cases)</span>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Calendar className="size-3.5" aria-hidden />
              {fmtDateTime(e.created_at)}
            </span>
            <span className="inline-flex items-center gap-1.5 font-mono">
              <Hash className="size-3.5" aria-hidden />
              {e.id}
            </span>
            {e.tags.length > 0 && (
              <span className="inline-flex items-center gap-1.5">
                <Tag className="size-3.5" aria-hidden />
                {e.tags.join(", ")}
              </span>
            )}
          </>
        }
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={urls.compare(null, e.id)}>
              <GitCompareArrows aria-hidden />
              Compare with…
            </Link>
          </Button>
        }
      />
      {e.is_demo && <DemoBanner variant="experiment" />}

      <KpiStrip className="2xl:grid-cols-8">
        <Kpi label="Overall score" value={fmtScore(s.overall_score)} sub="mean over cases" />
        <Kpi label="Pass rate" value={fmtPct(s.pass_rate)} sub="cases passing every metric" />
        <Kpi label="Cases" value={fmtInt(s.num_cases)} sub={`${fmtInt(s.num_evaluations)} evaluations`} />
        <Kpi
          label="Cost"
          value={fmtCost(s.cost_usd)}
          sub={s.cost_complete ? `${fmtCost(s.cost_per_case_usd)} per case` : "incomplete: some prices unknown"}
          hint="Judge spend in USD. LLM judge costs are estimated from list prices when the provider doesn't report them."
        />
        <Kpi label="Latency p50" value={fmtMs(s.latency_ms.p50)} sub={`p95 ${fmtMs(s.latency_ms.p95)}`} hint="Wall-clock time to evaluate one case, all metrics included." />
        <Kpi
          label="Jev acceptance"
          swatch="var(--route-jev)"
          value={fmtPct(s.routing.jev_acceptance_rate)}
          sub={`${fmtInt(s.routing.jev_accepted)} of ${fmtInt(s.routing.jev_attempts)} attempts`}
        />
        <Kpi
          label="Escalated to LLM"
          swatch="var(--route-esc)"
          value={fmtPct(s.routing.escalation_rate)}
          sub={`${fmtInt(s.routing.escalated)} judgments`}
        />
        <Kpi
          label="Jev / LLM agreement"
          value={fmtPct(s.agreement.agreement_rate)}
          sub={s.agreement.compared > 0 ? `on ${fmtInt(s.agreement.compared)} escalations` : "no escalations compared"}
          hint="On escalated judgments, how often Jev's pass/fail verdict matched the LLM judge's."
        />
      </KpiStrip>

      <Panel
        className="mt-6"
        title="Metrics"
        description="Mean score with the pass threshold marked. Distribution bins entirely below the threshold are tinted as failing."
      >
        <MetricMatrix metrics={metricOrder.map((m) => s.metrics[m])} thresholds={thresholds} />
      </Panel>

      <div className="mt-6 grid items-start gap-6 xl:grid-cols-5">
        <Panel className="xl:col-span-3" title="Routing" description="Where this experiment's judgments were decided." bodyClassName="px-4 pb-4">
          <RoutingCascade counts={routingCounts(s.routing)} />
        </Panel>
        <ConfigPanel experiment={e} className="xl:col-span-2" />
      </div>

      <Panel className="mt-6" title="Cases" description="Open a case to see its judgment chain and trace.">
        <CasesTable
          experimentId={e.id}
          metricOrder={metricOrder}
          metricNames={metricNames}
          filter={filter}
          page={page}
          onChange={setCases}
        />
      </Panel>
    </>
  );
}
