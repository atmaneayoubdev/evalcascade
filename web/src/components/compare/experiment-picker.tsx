"use client";

import { DemoTag } from "@/components/common/demo";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fmtShortDate } from "@/lib/format";
import type { ExperimentListItem } from "@/lib/types";

export function ExperimentPicker({
  id,
  label,
  value,
  onChange,
  experiments,
  exclude,
}: {
  id: string;
  label: string;
  value: string | null;
  onChange: (id: string) => void;
  experiments: ExperimentListItem[];
  exclude?: string | null;
}) {
  const known = value ? experiments.some((e) => e.id === value) : true;
  return (
    <div className="min-w-0 flex-1">
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium text-ink-2">
        {label}
      </label>
      <Select value={value ?? undefined} onValueChange={onChange}>
        <SelectTrigger id={id} className="h-9 w-full bg-surface text-[0.8125rem]">
          <SelectValue placeholder="Choose an experiment" />
        </SelectTrigger>
        <SelectContent position="popper" className="max-h-80 w-(--radix-select-trigger-width)">
          {!known && value && (
            <SelectItem value={value} disabled>
              <span className="font-mono text-xs">{value}</span>
            </SelectItem>
          )}
          {experiments.map((e) => (
            <SelectItem key={e.id} value={e.id} disabled={e.id === exclude}>
              <span className="flex min-w-0 items-center gap-2">
                <span className="truncate">{e.name}</span>
                {e.is_demo && <DemoTag />}
                <span className="shrink-0 text-2xs text-ink-3">
                  {e.dataset_name ?? "no dataset"}, {fmtShortDate(e.created_at)}
                </span>
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
