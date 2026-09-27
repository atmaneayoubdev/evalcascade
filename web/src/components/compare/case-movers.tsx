import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Panel } from "@/components/common/layout";
import { DeltaText } from "@/components/common/verdict";
import { fmtInt, fmtScore, fmtSigned } from "@/lib/format";
import type { CaseDelta, Comparison } from "@/lib/types";
import { urls } from "@/lib/urls";

export function CaseMovement({ cmp }: { cmp: Comparison }) {
  const c = cmp.cases;
  const parts = [
    { key: "improved", label: "Improved", n: c.improved, color: "var(--good)" },
    { key: "unchanged", label: "Unchanged", n: c.unchanged, color: "var(--route-none)" },
    { key: "regressed", label: "Regressed", n: c.regressed, color: "var(--bad)" },
  ];
  const total = c.matched || 1;
  return (
    <div>
      <div className="flex h-2.5 w-full gap-[2px]" role="img" aria-label={parts.map((p) => `${p.label} ${p.n}`).join(", ")}>
        {parts
          .filter((p) => p.n > 0)
          .map((p) => (
            <span
              key={p.key}
              className="h-full first:rounded-l-[3px] last:rounded-r-[3px]"
              style={{ flexGrow: p.n / total, flexBasis: 0, background: p.color }}
            />
          ))}
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-3 text-xs">
        {parts.map((p) => (
          <div key={p.key}>
            <dt className="flex items-center gap-1.5 text-ink-3">
              <span aria-hidden className="size-2 rounded-[2px]" style={{ background: p.color }} />
              {p.label}
            </dt>
            <dd className="tabular mt-0.5 text-base font-medium text-ink">{fmtInt(p.n)}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-ink-3">
        {fmtInt(c.matched)} cases matched by id.
        {(c.only_in_baseline > 0 || c.only_in_candidate > 0) &&
          ` ${fmtInt(c.only_in_baseline)} only in baseline, ${fmtInt(c.only_in_candidate)} only in candidate.`}
      </p>
    </div>
  );
}

function MoverList({ items, cmp, empty }: { items: CaseDelta[]; cmp: Comparison; empty: string }) {
  if (items.length === 0) return <p className="px-4 pb-4 text-xs text-ink-3">{empty}</p>;
  return (
    <ul className="divide-y divide-hairline border-t border-hairline">
      {items.map((d) => (
        <li key={d.case_id} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-3 px-4 py-2">
          <Link href={urls.caseView(cmp.candidate.id, d.case_id)} className="truncate font-mono text-xs font-medium text-ink hover:underline">
            {d.case_id}
          </Link>
          <span className="tabular flex items-center gap-1.5 text-xs text-ink-2">
            <Link href={urls.caseView(cmp.baseline.id, d.case_id)} className="hover:underline" title="Open in baseline">
              {fmtScore(d.baseline)}
            </Link>
            <ArrowRight className="size-3 text-ink-3" aria-label="to" />
            <Link href={urls.caseView(cmp.candidate.id, d.case_id)} className="text-ink hover:underline" title="Open in candidate">
              {fmtScore(d.candidate)}
            </Link>
          </span>
          <DeltaText delta={d.delta} better="higher" epsilon={0.0005} className="w-16 justify-end text-xs">
            {fmtSigned(d.delta)}
          </DeltaText>
        </li>
      ))}
    </ul>
  );
}

export function TopMovers({ cmp }: { cmp: Comparison }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title="Top regressions" description="Largest drops in case overall score. Scores link to each side's case view.">
        <MoverList items={cmp.cases.top_regressions} cmp={cmp} empty="No case got worse." />
      </Panel>
      <Panel title="Top improvements" description="Largest gains in case overall score.">
        <MoverList items={cmp.cases.top_improvements} cmp={cmp} empty="No case improved." />
      </Panel>
    </div>
  );
}
