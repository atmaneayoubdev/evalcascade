import { cn } from "cn";
import { fmtNum } from "@/lib/format";
import type { Answer } from "@/lib/types";

/**
 * Jev's confidence on a 0..1 scale with the escalation threshold as a marker.
 * The region left of the marker is where Jev hands the case to the LLM judge.
 */
export function ConfidenceMeter({
  value,
  threshold,
  className,
}: {
  value: number | null;
  threshold: number | null;
  className?: string;
}) {
  const v = value === null ? null : Math.max(0, Math.min(1, value));
  const t = threshold === null ? null : Math.max(0, Math.min(1, threshold));
  const below = v !== null && t !== null && v < t;
  return (
    <div className={cn("w-full", className)}>
      <div className="mb-1.5 flex items-baseline justify-between gap-3 text-xs">
        <span className="text-ink-3">
          Confidence <span className="tabular ml-1 text-sm font-semibold text-ink">{fmtNum(v, 2)}</span>
        </span>
        {t !== null && (
          <span className={cn("tabular", below ? "font-medium text-route-esc-ink" : "text-ink-3")}>
            {below ? "Below" : "Above"} escalation threshold {fmtNum(t, 2)}
          </span>
        )}
      </div>
      <div
        className="relative h-4"
        role="img"
        aria-label={`Confidence ${fmtNum(v, 2)}${t !== null ? `, escalate below ${fmtNum(t, 2)}` : ""}`}
      >
        <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 overflow-hidden rounded-full bg-sunken shadow-[inset_0_0_0_1px_var(--hairline)]">
          {t !== null && (
            <div
              className="absolute inset-y-0 left-0"
              style={{
                width: `${t * 100}%`,
                backgroundImage:
                  "repeating-linear-gradient(135deg, color-mix(in oklab, var(--route-esc) 30%, transparent) 0 2px, transparent 2px 5px)",
              }}
            />
          )}
          {v !== null && (
            <div
              className="absolute inset-y-0 left-0 rounded-full"
              style={{ width: `${v * 100}%`, background: "var(--route-jev)" }}
            />
          )}
        </div>
        {t !== null && (
          <div aria-hidden className="absolute top-0 h-4 w-[2px] -translate-x-1/2 rounded-full bg-ink" style={{ left: `${t * 100}%` }} />
        )}
      </div>
      <div className="tabular mt-0.5 flex justify-between text-[0.625rem] text-ink-3" aria-hidden>
        <span>0</span>
        <span>0.5</span>
        <span>1</span>
      </div>
    </div>
  );
}

function answerLabel(a: Answer): string {
  if (a.kind === "binary") return a.value ? "Yes" : "No";
  return String(a.value);
}

/** One question's answer: the chosen value plus, for Jev, its probability distribution. */
export function AnswerRow({
  answer,
  accent = "var(--route-jev)",
  label,
}: {
  answer: Answer;
  accent?: string;
  /** human label for the question; defaults to the raw question id */
  label?: { title: string; detail?: string };
}) {
  const probs =
    answer.probabilities && Object.keys(answer.probabilities).length > 0
      ? Object.entries(answer.probabilities)
      : answer.kind === "binary" && answer.probability !== null
        ? ([
            ["Yes", answer.probability],
            ["No", 1 - answer.probability],
          ] as [string, number][])
        : null;
  const chosen = answerLabel(answer);

  return (
    <div className="grid grid-cols-[minmax(5.5rem,8rem)_minmax(0,1fr)] items-start gap-x-3 gap-y-1 py-1.5">
      <div className="min-w-0 pt-px" title={`${answer.question_id} (${answer.kind})${label?.detail ? `: ${label.detail}` : ""}`}>
        {label ? (
          <>
            <div className="truncate text-[0.6875rem] font-medium text-ink-2">{label.title}</div>
            <div className="truncate text-2xs text-ink-3">{label.detail ?? answer.kind}</div>
          </>
        ) : (
          <>
            <div className="truncate font-mono text-[0.6875rem] text-ink-2">{answer.question_id}</div>
            <div className="text-2xs text-ink-3">{answer.kind}</div>
          </>
        )}
      </div>
      <div className="min-w-0">
        {probs ? (
          <div className="space-y-[3px]">
            {probs.map(([label, p]) => {
              const isChosen = label === chosen || (answer.kind === "score" && Number(label) === Number(answer.value));
              return (
                <div key={label} className="grid grid-cols-[4.75rem_minmax(0,1fr)_2.5rem] items-center gap-2 text-2xs">
                  <span className={cn("truncate", isChosen ? "font-semibold text-ink" : "text-ink-3")}>
                    {answer.kind === "score" ? `level ${label}` : label.replace(/_/g, " ")}
                  </span>
                  <span className="relative h-1.5 overflow-hidden rounded-full bg-sunken">
                    <span
                      className="absolute inset-y-0 left-0 rounded-full"
                      style={{ width: `${Math.max(0, Math.min(1, p)) * 100}%`, background: accent, opacity: isChosen ? 1 : 0.38 }}
                    />
                  </span>
                  <span className={cn("tabular text-right", isChosen ? "text-ink" : "text-ink-3")}>{p.toFixed(2)}</span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-wrap items-baseline gap-x-2 text-xs">
            <span className="font-medium text-ink">{chosen.replace(/_/g, " ")}</span>
            <span className="tabular text-ink-3">score {answer.score.toFixed(2)}</span>
            {answer.confidence !== null && (
              <span className="tabular text-ink-3">
                confidence {answer.confidence.toFixed(2)}
                {answer.confidence_source === "self_reported" ? " (self-reported)" : ""}
              </span>
            )}
          </div>
        )}
        {answer.explanation && <p className="mt-1 text-xs text-ink-2">{answer.explanation}</p>}
      </div>
    </div>
  );
}
