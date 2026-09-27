import { formatParam } from "@/components/common/controls";
import { KeyValues, Panel } from "@/components/common/layout";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Experiment, PolicyConfig } from "@/lib/types";

export function PolicyValues({ policy }: { policy: PolicyConfig }) {
  return (
    <KeyValues
      items={[
        { label: "Deterministic checks first", value: formatParam(policy.deterministic_first) },
        { label: "Primary evaluator", value: policy.primary ?? "—", mono: true },
        { label: "Fallback evaluator", value: policy.fallback ?? "—", mono: true },
        { label: "Escalate below confidence", value: <span className="tabular">{policy.escalate_below.toFixed(2)}</span> },
        { label: "Escalate on primary error", value: formatParam(policy.escalate_on_error) },
        { label: "Reasoning metrics go to fallback", value: formatParam(policy.route_reasoning_to_fallback) },
      ]}
    />
  );
}

export function PolicyOverrides({ overrides }: { overrides: PolicyConfig["overrides"] }) {
  const entries = Object.entries(overrides);
  if (!entries.length) return <p className="px-4 py-3 text-xs text-ink-3">No per-metric overrides.</p>;
  return (
    <ul className="divide-y divide-hairline">
      {entries.map(([metric, o]) => (
        <li key={metric} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2 text-[0.8125rem]">
          <span className="font-mono text-xs text-ink">{metric}</span>
          {Object.entries(o).map(([k, v]) => (
            <span key={k} className="text-xs text-ink-2">
              {k} <span className="tabular font-medium text-ink">{formatParam(v)}</span>
            </span>
          ))}
        </li>
      ))}
    </ul>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="border-t border-hairline bg-sunken/60 px-4 py-2 text-xs font-medium text-ink-2">{children}</h3>;
}

/** Everything that produced this experiment: routing policy, evaluators, metric params, dataset. */
export function ConfigPanel({ experiment: e, className }: { experiment: Experiment; className?: string }) {
  const paramKeys = Array.from(new Set(e.metrics.flatMap((m) => Object.keys(m.params))));
  const ordered = ["threshold", "weight", "escalate_below", ...paramKeys.filter((k) => !["threshold", "weight", "escalate_below"].includes(k))].filter(
    (k) => paramKeys.includes(k),
  );
  return (
    <Panel className={className} title="Configuration" description="How this run was judged. Recorded with the experiment.">
      <Tabs defaultValue="policy" className="gap-0">
        <div className="border-b border-hairline px-4">
          <TabsList variant="line" className="h-9 flex-wrap">
            <TabsTrigger value="policy">Policy</TabsTrigger>
            <TabsTrigger value="evaluators">Evaluators</TabsTrigger>
            <TabsTrigger value="metrics">Metric params</TabsTrigger>
            <TabsTrigger value="dataset">Dataset</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="policy">
          <PolicyValues policy={e.policy} />
          <SubHeading>Per-metric overrides</SubHeading>
          <PolicyOverrides overrides={e.policy.overrides} />
        </TabsContent>

        <TabsContent value="evaluators">
          {Object.keys(e.evaluators).length === 0 ? (
            <p className="px-4 py-3 text-xs text-ink-3">No evaluator settings recorded.</p>
          ) : (
            <ul className="divide-y divide-hairline">
              {Object.entries(e.evaluators).map(([name, cfg]) => (
                <li key={name} className="px-4 py-2.5">
                  <div className="font-mono text-xs font-medium text-ink">{name}</div>
                  <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-ink-2">
                    {Object.entries(cfg).length === 0 && <span className="text-ink-3">defaults</span>}
                    {Object.entries(cfg).map(([k, v]) => (
                      <span key={k}>
                        <span className="text-ink-3">{k}</span> <span className="break-all text-ink">{formatParam(v)}</span>
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="metrics">
          <Table>
            <TableHeader className="bg-transparent">
              <TableRow>
                <TableHead className="pl-4">Metric</TableHead>
                {ordered.map((k) => (
                  <TableHead key={k} className="text-right last:pr-4">
                    {k}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {e.metrics.map((m) => (
                <TableRow key={m.name}>
                  <TableCell className="pl-4 font-mono text-xs">{m.name}</TableCell>
                  {ordered.map((k) => (
                    <TableCell key={k} className="tabular text-right text-xs last:pr-4">
                      {k in m.params ? formatParam(m.params[k]) : <span className="text-ink-3">default</span>}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TabsContent>

        <TabsContent value="dataset">
          <KeyValues
            items={[
              { label: "Name", value: e.dataset.name ?? "—" },
              { label: "Path", value: e.dataset.path ?? "—", mono: true },
              { label: "Hash", value: e.dataset.hash ?? "—", mono: true },
              { label: "Cases", value: e.dataset.size },
              { label: "EvalCascade version", value: e.version, mono: true },
            ]}
          />
          {e.notes && (
            <>
              <SubHeading>Notes</SubHeading>
              <p className="px-4 py-3 text-[0.8125rem] text-ink-2">{e.notes}</p>
            </>
          )}
        </TabsContent>
      </Tabs>
    </Panel>
  );
}
