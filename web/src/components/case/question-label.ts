import { humanize, truncate } from "@/lib/format";
import type { Case } from "@/lib/types";

export interface QuestionLabel {
  title: string;
  detail?: string;
}

/**
 * Human label for an Answer.question_id. The backend uses `relevance`,
 * `groundedness`, `category`, …, plus indexed ids: `p1..pN` (context passages),
 * `s1..` (sentences of the output), `c1..` (citations) and `call_1..` (the k-th
 * tool call of the trace). Indexed ids are resolved against the case when possible.
 */
export function questionLabel(questionId: string, c?: Case | null): QuestionLabel {
  let m = /^p(\d+)$/i.exec(questionId) ?? /^(?:passage|chunk|context|doc)[_-]?(\d+)$/i.exec(questionId);
  if (m) {
    const n = Number(m[1]);
    const text = c?.context[n - 1];
    return { title: `Passage ${n}`, detail: text ? truncate(text, 80) : undefined };
  }
  m = /^call[_-]?(\d+)$/i.exec(questionId);
  if (m) {
    const k = Number(m[1]);
    const calls = (c?.trace?.steps ?? [])
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => s.tool_call !== null);
    const hit = calls[k - 1];
    return {
      title: `Tool call ${k}`,
      detail: hit?.s.tool_call ? `${hit.s.tool_call.name}, step ${hit.i + 1}` : undefined,
    };
  }
  m = /^s(\d+)$/i.exec(questionId);
  if (m) return { title: `Sentence ${Number(m[1])}`, detail: "of the output" };
  m = /^c(\d+)$/i.exec(questionId);
  if (m) return { title: `Citation ${Number(m[1])}` };
  return { title: humanize(questionId) };
}

/** Index (0-based) of the context passage a question id refers to, if any. */
export function passageIndex(questionId: string): number | null {
  const m = /^p(\d+)$/i.exec(questionId) ?? /^(?:passage|chunk|context|doc)[_-]?(\d+)$/i.exec(questionId);
  return m ? Number(m[1]) - 1 : null;
}
