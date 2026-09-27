/** Display formatting. Every formatter accepts null and renders an em dash for it. */

export const EMPTY = "—";

const isNum = (v: number | null | undefined): v is number =>
  typeof v === "number" && Number.isFinite(v);

/** Normalized 0..1 score → "0.842". */
export function fmtScore(v: number | null | undefined, digits = 3): string {
  return isNum(v) ? v.toFixed(digits) : EMPTY;
}

/** 0..1 rate → "84.2%". */
export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (!isNum(v)) return EMPTY;
  const pct = v * 100;
  return `${pct.toFixed(pct !== 0 && Math.abs(pct) < 1 && digits < 2 ? 2 : digits)}%`;
}

/** USD with precision that scales with magnitude: $12.40, $0.0831, $0.00042. */
export function fmtCost(v: number | null | undefined): string {
  if (!isNum(v)) return EMPTY;
  if (v === 0) return "$0";
  const abs = Math.abs(v);
  if (abs >= 100) return `$${v.toFixed(0)}`;
  if (abs >= 1) return `$${v.toFixed(2)}`;
  if (abs >= 0.01) return `$${v.toFixed(3)}`;
  return `$${v.toPrecision(2).replace(/0+$/, "").replace(/\.$/, "")}`;
}

/** Milliseconds → "842 ms" / "1.24 s" / "2m 05s". */
export function fmtMs(v: number | null | undefined): string {
  if (!isNum(v)) return EMPTY;
  if (v < 1) return `${v.toFixed(2)} ms`;
  if (v < 1000) return `${Math.round(v)} ms`;
  if (v < 60_000) return `${(v / 1000).toFixed(v < 10_000 ? 2 : 1)} s`;
  const m = Math.floor(v / 60_000);
  const s = Math.round((v % 60_000) / 1000);
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export function fmtInt(v: number | null | undefined): string {
  return isNum(v) ? Math.round(v).toLocaleString("en-US") : EMPTY;
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  return isNum(v) ? v.toFixed(digits) : EMPTY;
}

/** Signed delta for scores: "+0.031" / "−0.012". Uses a true minus sign. */
export function fmtSigned(v: number | null | undefined, digits = 3): string {
  if (!isNum(v)) return EMPTY;
  const s = Math.abs(v).toFixed(digits);
  if (Number(s) === 0) return `±${s}`;
  return `${v > 0 ? "+" : "−"}${s}`;
}

/** Signed delta for 0..1 rates, in percentage points: "+3.1 pp". */
export function fmtSignedPp(v: number | null | undefined, digits = 1): string {
  if (!isNum(v)) return EMPTY;
  return `${fmtSigned(v * 100, digits)} pp`;
}

/** Relative change: "+12.4%". */
export function fmtRelative(v: number | null | undefined): string {
  if (!isNum(v)) return EMPTY;
  return `${fmtSigned(v * 100, 1)}%`;
}

export function fmtSignedCost(v: number | null | undefined): string {
  if (!isNum(v)) return EMPTY;
  if (v === 0) return "±$0";
  return `${v > 0 ? "+" : "−"}${fmtCost(Math.abs(v))}`;
}

export function fmtSignedMs(v: number | null | undefined): string {
  if (!isNum(v)) return EMPTY;
  if (Math.round(v) === 0) return "±0 ms";
  return `${v > 0 ? "+" : "−"}${fmtMs(Math.abs(v))}`;
}

const dateFmt = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});
const dateTimeFmt = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const shortDateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDate(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? dateFmt.format(d) : EMPTY;
}

export function fmtDateTime(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? dateTimeFmt.format(d) : EMPTY;
}

export function fmtShortDate(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? shortDateFmt.format(d) : EMPTY;
}

/** "3 days ago" style, relative to `now`. */
export function fmtRelativeTime(iso: string | null | undefined, now = Date.now()): string {
  const d = parse(iso);
  if (!d) return EMPTY;
  const diff = (now - d.getTime()) / 1000;
  if (diff < 0) return fmtDateTime(iso);
  if (diff < 60) return "just now";
  const units: [number, string][] = [
    [60, "minute"],
    [3600, "hour"],
    [86400, "day"],
    [86400 * 30, "month"],
    [86400 * 365, "year"],
  ];
  for (let i = units.length - 1; i >= 0; i--) {
    const [secs, name] = units[i];
    if (diff >= secs) {
      const n = Math.floor(diff / secs);
      return `${n} ${name}${n === 1 ? "" : "s"} ago`;
    }
  }
  return fmtDateTime(iso);
}

export function titleCase(s: string): string {
  return s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function humanize(s: string): string {
  const t = s.replace(/[_-]+/g, " ").trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function truncate(s: string | null | undefined, n: number): string {
  if (!s) return "";
  return s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s;
}

export const CATEGORY_LABEL = { general: "General", rag: "RAG", agent: "Agent" } as const;
