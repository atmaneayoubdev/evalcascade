import { JsonBlock } from "@/components/common/code";
import { Panel } from "@/components/common/layout";
import type { Case, MetricResult, ToolSpec } from "@/lib/types";
import { passageIndex } from "./question-label";

function TextBlock({ label, text, empty = "Not provided." }: { label: string; text: string | null; empty?: string }) {
  return (
    <div className="px-4 py-3">
      <div className="mb-1 text-2xs font-medium text-ink-3">{label}</div>
      {text ? (
        <p className="max-w-[80ch] text-[0.8125rem] leading-relaxed whitespace-pre-wrap text-ink">{text}</p>
      ) : (
        <p className="text-xs text-ink-3">{empty}</p>
      )}
    </div>
  );
}

function expectedText(expected: Case["expected"]): string | null {
  if (!expected) return null;
  const keys = Object.keys(expected);
  if (keys.length === 1 && typeof expected[keys[0]] === "string") return expected[keys[0]] as string;
  return null;
}

/** Per-passage answers (question ids p1..pN), if any metric produced them. */
function passageScores(metrics: MetricResult[]): Map<number, { metric: string; score: number }[]> {
  const out = new Map<number, { metric: string; score: number }[]>();
  for (const m of metrics) {
    const final = m.judgments[m.judgments.length - 1];
    if (!final) continue;
    for (const a of Object.values(final.answers)) {
      const idx = passageIndex(a.question_id);
      if (idx === null) continue;
      const list = out.get(idx) ?? [];
      list.push({ metric: m.display_name, score: a.score });
      out.set(idx, list);
    }
  }
  return out;
}

export function CaseContent({ c, metrics }: { c: Case; metrics: MetricResult[] }) {
  const exp = expectedText(c.expected);
  const scores = passageScores(metrics);
  const hasContext = c.context.length > 0;
  return (
    <div className={hasContext ? "grid items-start gap-6 xl:grid-cols-2" : "grid gap-6"}>
      <Panel title="Input and output" bodyClassName="divide-y divide-hairline border-t border-hairline">
        <TextBlock label="Input" text={c.input} />
        <TextBlock label="Output" text={c.output} />
        <div className="px-4 py-3">
          <div className="mb-1 text-2xs font-medium text-ink-3">Expected</div>
          {!c.expected ? (
            <p className="text-xs text-ink-3">No expected value in the dataset.</p>
          ) : exp ? (
            <p className="text-[0.8125rem] leading-relaxed text-ink">{exp}</p>
          ) : (
            <JsonBlock value={c.expected} maxHeight={200} />
          )}
        </div>
        {Object.keys(c.metadata).length > 0 && (
          <details className="group px-4 py-2.5">
            <summary className="cursor-pointer rounded-sm text-2xs font-medium text-ink-3 hover:text-ink">Case metadata</summary>
            <JsonBlock value={c.metadata} className="mt-2" maxHeight={180} />
          </details>
        )}
      </Panel>

      {hasContext && (
        <Panel title="Retrieved context" description={`${c.context.length} passage${c.context.length > 1 ? "s" : ""}, in retrieval order.`}>
          <ol className="divide-y divide-hairline border-t border-hairline">
            {c.context.map((p, i) => (
              <li key={i} className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-2 px-4 py-3">
                <span className="tabular pt-px text-xs font-medium text-ink-3">[{i + 1}]</span>
                <div className="min-w-0">
                  <p className="text-[0.8125rem] leading-relaxed whitespace-pre-wrap text-ink">{p}</p>
                  {scores.get(i)?.map((s) => (
                    <span key={s.metric} className="tabular mt-1.5 mr-2 inline-flex items-center gap-1.5 text-2xs text-ink-3">
                      {s.metric}
                      <span className="relative h-1 w-12 overflow-hidden rounded-full bg-sunken">
                        <span className="absolute inset-y-0 left-0 rounded-full bg-ink-2" style={{ width: `${s.score * 100}%` }} />
                      </span>
                      <span className="text-ink-2">{s.score.toFixed(2)}</span>
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ol>
        </Panel>
      )}
    </div>
  );
}

export function ToolList({ tools }: { tools: ToolSpec[] }) {
  if (!tools.length) return <p className="px-4 pb-4 text-xs text-ink-3">No tool specs recorded with the trace.</p>;
  return (
    <ul className="divide-y divide-hairline border-t border-hairline">
      {tools.map((t) => (
        <li key={t.name} className="px-4 py-2.5">
          <details className="group">
            <summary className="flex cursor-pointer list-none items-baseline gap-2 rounded-sm">
              <code className="font-mono text-xs font-medium text-ink">{t.name}</code>
              <span className="min-w-0 truncate text-xs text-ink-3">{t.description}</span>
            </summary>
            {t.parameters && <JsonBlock value={t.parameters} className="mt-2" maxHeight={220} />}
          </details>
        </li>
      ))}
    </ul>
  );
}
