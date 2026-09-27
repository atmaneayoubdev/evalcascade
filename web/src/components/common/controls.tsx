"use client";

import { useId } from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { cn } from "cn";
import { Switch } from "@/components/ui/switch";
import { TableHead } from "@/components/ui/table";

export function DemoToggle({
  checked,
  onCheckedChange,
  className,
}: {
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn("flex items-center gap-2 rounded-md border border-hairline bg-surface px-2.5 py-1.5", className)}>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} size="sm" />
      <label htmlFor={id} className="cursor-pointer text-xs font-medium text-ink-2 select-none">
        Include demo data
      </label>
    </div>
  );
}

/** Segmented single-choice control (filters, modes). */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode }[];
  label: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("inline-flex rounded-md border border-hairline bg-sunken p-0.5 text-xs", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-[5px] px-2.5 py-1 font-medium text-ink-3 transition-colors hover:text-ink",
            value === o.value && "bg-surface text-ink shadow-[0_0_0_1px_var(--hairline)]",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Render an arbitrary config value compactly. */
export function formatParam(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(Number(v.toFixed(4)));
  if (typeof v === "string") return v;
  return JSON.stringify(v);
}

export type SortDir = "asc" | "desc";

export function SortableHead<K extends string>({
  label,
  sortKey,
  sort,
  onSort,
  align = "left",
  className,
  defaultDir = "desc",
}: {
  label: string;
  sortKey: K;
  sort: { key: K; dir: SortDir };
  onSort: (next: { key: K; dir: SortDir }) => void;
  align?: "left" | "right";
  className?: string;
  defaultDir?: SortDir;
}) {
  const active = sort.key === sortKey;
  const Icon = !active ? ChevronsUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead
      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
      className={cn(align === "right" && "text-right", className)}
    >
      <button
        type="button"
        onClick={() => onSort({ key: sortKey, dir: active ? (sort.dir === "asc" ? "desc" : "asc") : defaultDir })}
        className={cn(
          "inline-flex items-center gap-1 rounded-sm hover:text-ink",
          align === "right" && "flex-row-reverse",
          active && "text-ink",
        )}
      >
        {label}
        <Icon className={cn("size-3", !active && "opacity-50")} aria-hidden />
      </button>
    </TableHead>
  );
}

/** Numeric/text comparator that always sorts nulls last. */
export function compareValues(a: number | string | null | undefined, b: number | string | null | undefined, dir: SortDir) {
  const an = a === null || a === undefined;
  const bn = b === null || b === undefined;
  if (an && bn) return 0;
  if (an) return 1;
  if (bn) return -1;
  const r = typeof a === "string" && typeof b === "string" ? a.localeCompare(b) : Number(a) - Number(b);
  return dir === "asc" ? r : -r;
}
