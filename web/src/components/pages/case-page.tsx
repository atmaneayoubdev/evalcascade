"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { CaseContent, ToolList } from "@/components/case/case-content";
import { MetricJudgmentCard } from "@/components/case/judgment-chain";
import { TraceTimeline } from "@/components/case/trace-timeline";
import { DemoBanner, DemoMaybe } from "@/components/common/demo";
import { Kpi, KpiStrip } from "@/components/common/kpi";
import { PageHeader, Panel, SectionTitle } from "@/components/common/layout";
import { RouteDot, RouteLegend } from "@/components/common/route";
import { ErrorState, NotFoundState, PageSkeleton } from "@/components/common/states";
import { PassBadge } from "@/components/common/verdict";
import { Button } from "@/components/ui/button";
import { useApi } from "@/hooks/use-api";
import { recentCase, recentExperiment } from "@/hooks/use-stored";
import { api } from "@/lib/api";
import { fmtCost, fmtInt, fmtMs, fmtScore } from "@/lib/format";
import { urls } from "@/lib/urls";

export function CasePage() {
  const params = useSearchParams();
  const expId = params.get("experiment");
  const caseId = params.get("case");
  const valid = Boolean(expId && caseId);

  const result = useApi(valid ? `case:${expId}:${caseId}` : null, () => api.caseResult(expId!, caseId!));
  const exp = useApi(expId ? `experiment:${expId}` : null, () => api.experiment(expId!));
  // Neighbours for previous/next navigation (local API, so one large page is cheap).
  const siblings = useApi(expId ? `case-ids:${expId}` : null, () => api.cases(expId!, { limit: 500, offset: 0 }));

  const r = result.data;
  const e = exp.data;

  useEffect(() => {
    if (!r || !expId || !caseId) return;
    recentCase.set(JSON.stringify({ experiment: expId, case: caseId }));
    document.title = `${caseId} | EvalCascade`;
  }, [r, expId, caseId]);
  useEffect(() => {
    if (e) recentExperiment.set(JSON.stringify({ id: e.id, name: e.name }));
  }, [e]);

  const nav = useMemo(() => {
    const ids = siblings.data?.items.map((c) => c.case_id) ?? [];
    const i = caseId ? ids.indexOf(caseId) : -1;
    return { prev: i > 0 ? ids[i - 1] : null, next: i >= 0 && i < ids.length - 1 ? ids[i + 1] : null, index: i, total: ids.length };
  }, [siblings.data, caseId]);

  const crumbs = [
    { label: "Experiments", href: urls.experiments() },
    ...(expId ? [{ label: e?.name ?? expId, href: urls.experiment(expId) }] : []),
    { label: caseId ?? "Case" },
  ];

  if (!valid) {
    return (
      <>
        <PageHeader title="Case" crumbs={crumbs} />
        <NotFoundState what="This case" detail="The link needs both an experiment and a case id. Open a case from an experiment's case table." />
      </>
    );
  }
  if (result.error) {
    return (
      <>
        <PageHeader title={`Case ${caseId}`} crumbs={crumbs} />
        {result.error.kind === "not_found" ? (
          <NotFoundState what="This case" detail={result.error.detail ?? `No case “${caseId}” in experiment “${expId}”.`} />
        ) : (
          <ErrorState error={result.error} onRetry={result.reload} />
        )}
      </>
    );
  }
  if (!r) return <PageSkeleton kpis={5} panels={3} />;

  const c = r.case;
  const metrics = r.metrics;

  return (
    <>
      <PageHeader
        crumbs={crumbs}
        title={<span className="font-mono text-[1.25rem] tracking-[-0.01em]">{r.case_id ?? c.id}</span>}
        badge={
          <span className="flex items-center gap-2">
            <PassBadge passed={r.passed} />
            {e && <DemoMaybe isDemo={e.is_demo} />}
          </span>
        }
        description={
          e ? (
            <>
              In <Link href={urls.experiment(e.id)} className="font-medium text-ink hover:underline">{e.name}</Link>
              {e.dataset_name && <> on {e.dataset_name}</>}
            </>
          ) : undefined
        }
        actions={
          nav.total > 0 && (
            <div className="flex items-center gap-1">
              <Button asChild={Boolean(nav.prev)} variant="outline" size="sm" disabled={!nav.prev}>
                {nav.prev ? (
                  <Link href={urls.caseView(expId!, nav.prev)} aria-label={`Previous case ${nav.prev}`}>
                    <ChevronLeft aria-hidden />
                    Previous
                  </Link>
                ) : (
                  <span>
                    <ChevronLeft aria-hidden />
                    Previous
                  </span>
                )}
              </Button>
              <span className="tabular px-1.5 text-xs text-ink-3">
                {nav.index + 1} of {nav.total}
              </span>
              <Button asChild={Boolean(nav.next)} variant="outline" size="sm" disabled={!nav.next}>
                {nav.next ? (
                  <Link href={urls.caseView(expId!, nav.next)} aria-label={`Next case ${nav.next}`}>
                    Next
                    <ChevronRight aria-hidden />
                  </Link>
                ) : (
                  <span>
                    Next
                    <ChevronRight aria-hidden />
                  </span>
                )}
              </Button>
            </div>
          )
        }
      />
      {e?.is_demo && <DemoBanner variant="experiment" />}
      {r.error && (
        <div role="alert" className="mb-6 rounded-xl border border-bad/40 bg-surface px-4 py-3 text-[0.8125rem] text-bad-ink">
          Case error: {r.error}
        </div>
      )}

      <KpiStrip className="lg:grid-cols-5">
        <Kpi label="Overall score" value={fmtScore(r.overall_score)} sub={r.passed === null ? "not judged" : r.passed ? "passed every metric" : "failed at least one metric"} />
        <Kpi label="Metrics" value={`${metrics.filter((m) => m.passed).length} / ${metrics.filter((m) => m.status === "ok").length}`} sub="passed / judged" />
        <Kpi label="Escalations" swatch="var(--route-esc)" value={fmtInt(r.escalations)} sub="Jev handed to the LLM judge" />
        <Kpi label="Latency" value={fmtMs(r.latency_ms)} sub="wall clock, all metrics" />
        <Kpi label="Cost" value={fmtCost(r.cost_usd)} sub="all judge calls" />
      </KpiStrip>

      <nav aria-label="Metrics in this case" className="mt-4 flex flex-wrap gap-1.5">
        {metrics.map((m) => (
          <a
            key={m.metric}
            href={`#metric-${m.metric}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-surface px-2 py-1 text-xs text-ink-2 hover:text-ink"
          >
            <RouteDot route={m.route} />
            {m.display_name}
            <span className={m.passed === false ? "tabular font-medium text-bad-ink" : "tabular text-ink-3"}>
              {m.status === "ok" ? fmtScore(m.score, 2) : m.status}
            </span>
          </a>
        ))}
      </nav>

      <div className="mt-6">
        <CaseContent c={c} metrics={metrics} />
      </div>

      {c.trace && (
        <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <Panel title="Agent trace" description="Each step with the verdicts metrics gave it." bodyClassName="px-4 pb-4">
            <TraceTimeline trace={c.trace} metrics={metrics} />
          </Panel>
          <Panel title="Available tools" description={`${c.trace.tools.length} tools offered to the agent.`}>
            <ToolList tools={c.trace.tools} />
          </Panel>
        </div>
      )}

      <SectionTitle aside={<RouteLegend />}>Judgments</SectionTitle>
      <div className="space-y-4">
        {metrics.map((m) => (
          <MetricJudgmentCard key={m.metric} metric={m} caseData={c} />
        ))}
      </div>
    </>
  );
}
