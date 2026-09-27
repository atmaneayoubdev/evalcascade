"use client";

import { useMemo, useState } from "react";
import { BookOpenCheck, Search } from "lucide-react";
import { cn } from "cn";
import { PageHeader, Panel } from "@/components/common/layout";
import { RouteDot } from "@/components/common/route";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/common/states";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { api } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/format";
import type { MetricCategory, MetricInfo } from "@/lib/types";

const CATEGORY_ORDER: MetricCategory[] = ["general", "rag", "agent"];
const CATEGORY_NOTE: Record<MetricCategory, string> = {
  general: "Work on any input and output.",
  rag: "Need retrieved context passages.",
  agent: "Read an agent trace: steps, tool calls and results.",
};

const DET: Record<MetricInfo["deterministic"], { label: string; note: string; filled: number }> = {
  full: { label: "Full", note: "Always settled by rules. No model call.", filled: 2 },
  partial: { label: "Partial", note: "Rules settle clear-cut cases; the rest go to Jev.", filled: 1 },
  none: { label: "None", note: "Always judged by a model.", filled: 0 },
};

function Chip({ children, mono }: { children: React.ReactNode; mono?: boolean }) {
  return (
    <span className={cn("inline-flex h-5 items-center rounded-[4px] border border-hairline bg-sunken px-1.5 text-2xs text-ink-2", mono && "font-mono")}>
      {children}
    </span>
  );
}

function DeterministicSupport({ level }: { level: MetricInfo["deterministic"] }) {
  const d = DET[level];
  return (
    <div className="flex items-start gap-2" title={d.note}>
      <span className="mt-1 flex gap-0.5" aria-hidden>
        {[0, 1].map((i) => (
          <span
            key={i}
            className="size-2 rounded-full border"
            style={{
              background: i < d.filled ? "var(--route-det)" : "transparent",
              borderColor: i < d.filled ? "var(--route-det)" : "var(--hairline-strong)",
            }}
          />
        ))}
      </span>
      <span>
        <span className="block text-xs font-medium text-ink">{d.label}</span>
        <span className="block text-2xs text-ink-3">{d.note}</span>
      </span>
    </div>
  );
}

function MetricRow({ m }: { m: MetricInfo }) {
  return (
    <li className="grid gap-x-6 gap-y-3 px-4 py-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,0.9fr)]">
      <div className="min-w-0">
        <h3 className="text-[0.875rem] font-semibold text-ink">{m.display_name}</h3>
        <p className="font-mono text-2xs text-ink-3">{m.name}</p>
        <p className="mt-1.5 max-w-[60ch] text-[0.8125rem] leading-relaxed text-ink-2">{m.description}</p>
      </div>
      <dl className="grid content-start gap-2.5 text-xs">
        <div>
          <dt className="mb-1 text-2xs text-ink-3">Question types</dt>
          <dd className="flex flex-wrap gap-1">
            {m.primitives.map((p) => (
              <Chip key={p}>{p}</Chip>
            ))}
          </dd>
        </div>
        <div>
          <dt className="mb-1 text-2xs text-ink-3">Required fields</dt>
          <dd className="flex flex-wrap gap-1">
            {m.required_fields.length ? m.required_fields.map((f) => <Chip key={f} mono>{f}</Chip>) : <span className="text-ink-3">none</span>}
          </dd>
        </div>
        {m.optional_fields.length > 0 && (
          <div>
            <dt className="mb-1 text-2xs text-ink-3">Optional fields</dt>
            <dd className="flex flex-wrap gap-1">
              {m.optional_fields.map((f) => (
                <Chip key={f} mono>
                  {f}
                </Chip>
              ))}
            </dd>
          </div>
        )}
      </dl>
      <dl className="grid content-start gap-2.5">
        <div>
          <dt className="mb-1 text-2xs text-ink-3">Deterministic support</dt>
          <dd>
            <DeterministicSupport level={m.deterministic} />
          </dd>
        </div>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <div>
            <dt className="text-2xs text-ink-3">Default threshold</dt>
            <dd className="tabular text-sm font-medium text-ink">{m.default_threshold.toFixed(2)}</dd>
          </div>
          <div>
            <dt className="text-2xs text-ink-3">Model route</dt>
            <dd className="flex items-center gap-1.5 text-xs text-ink">
              <RouteDot route={m.requires_reasoning ? "llm" : "jev"} />
              {m.requires_reasoning ? "Requires reasoning: LLM judge" : "Jev first"}
            </dd>
          </div>
        </div>
      </dl>
    </li>
  );
}

export function MetricsPage() {
  const { data, error, reload } = useApi("metrics", () => api.metrics());
  const [q, setQ] = useState("");
  const groups = useMemo(() => {
    const query = q.trim().toLowerCase();
    const list = (data ?? []).filter(
      (m) =>
        !query ||
        m.name.toLowerCase().includes(query) ||
        m.display_name.toLowerCase().includes(query) ||
        m.description.toLowerCase().includes(query),
    );
    return CATEGORY_ORDER.map((c) => ({ category: c, metrics: list.filter((m) => m.category === c) })).filter((g) => g.metrics.length);
  }, [data, q]);

  const header = (
    <PageHeader
      title="Metrics"
      description="Every built-in metric: what it measures, what it needs from a case, and how much of it rules can decide before a model is asked."
      actions={
        data && data.length > 0 ? (
          <div className="relative w-64">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" aria-hidden />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search metrics" aria-label="Search metrics" className="h-8 bg-surface pl-8 text-[0.8125rem]" />
          </div>
        ) : undefined
      }
    />
  );

  if (error)
    return (
      <>
        {header}
        <ErrorState error={error} onRetry={reload} />
      </>
    );
  if (!data) return <PageSkeleton kpis={0} panels={3} />;
  if (data.length === 0)
    return (
      <>
        {header}
        <EmptyState icon={<BookOpenCheck className="size-4.5" aria-hidden />} title="No metrics registered">
          <p>The server reported an empty metric catalog.</p>
        </EmptyState>
      </>
    );

  return (
    <>
      {header}
      {groups.length === 0 && <p className="py-10 text-center text-xs text-ink-3">No metrics match “{q}”.</p>}
      <div className="space-y-6">
        {groups.map((g) => (
          <Panel
            key={g.category}
            title={
              <span className="flex items-baseline gap-2">
                {CATEGORY_LABEL[g.category]}
                <span className="tabular text-xs font-normal text-ink-3">{g.metrics.length}</span>
              </span>
            }
            description={CATEGORY_NOTE[g.category]}
          >
            <ul className="divide-y divide-hairline border-t border-hairline">
              {g.metrics.map((m) => (
                <MetricRow key={m.name} m={m} />
              ))}
            </ul>
          </Panel>
        ))}
      </div>
    </>
  );
}
