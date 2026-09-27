"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo } from "react";
import {
  BookOpenCheck,
  FlaskConical,
  GitCompareArrows,
  LayoutGrid,
  ListTree,
  Settings2,
  SquareChartGantt,
  type LucideIcon,
} from "lucide-react";
import { cn } from "cn";
import { recentCase, recentExperiment, useStored } from "@/hooks/use-stored";
import { urls } from "@/lib/urls";
import { ApiStatus } from "./api-status";
import { Logo } from "./logo";
import { ThemeToggle } from "./theme";

interface NavItem {
  href: string | null;
  match: string;
  label: string;
  Icon: LucideIcon;
  sub?: boolean;
  hint?: string;
}

function parse<T>(raw: string): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

const strip = (p: string) => (p.length > 1 ? p.replace(/\/+$/, "") : p);

export function useNavItems(): NavItem[] {
  const [expRaw] = useStored(recentExperiment);
  const [caseRaw] = useStored(recentCase);
  return useMemo(() => {
    const exp = parse<{ id: string; name: string }>(expRaw);
    const cs = parse<{ experiment: string; case: string }>(caseRaw);
    return [
      { href: urls.overview(), match: "/", label: "Overview", Icon: LayoutGrid },
      { href: urls.experiments(), match: "/experiments", label: "Experiments", Icon: FlaskConical },
      {
        href: exp ? urls.experiment(exp.id) : null,
        match: "/experiments/view",
        label: "Experiment details",
        Icon: SquareChartGantt,
        sub: true,
        hint: exp ? exp.name : "Open an experiment first",
      },
      {
        href: cs ? urls.caseView(cs.experiment, cs.case) : null,
        match: "/cases/view",
        label: "Case trace",
        Icon: ListTree,
        sub: true,
        hint: cs ? cs.case : "Open a case first",
      },
      { href: urls.compare(), match: "/compare", label: "Compare", Icon: GitCompareArrows },
      { href: urls.metrics(), match: "/metrics", label: "Metrics", Icon: BookOpenCheck },
      { href: urls.settings(), match: "/settings", label: "Settings", Icon: Settings2 },
    ];
  }, [expRaw, caseRaw]);
}

function isActive(pathname: string, item: NavItem) {
  const p = strip(pathname);
  if (item.match === "/") return p === "/";
  if (item.match === "/experiments") return p === "/experiments";
  return p === item.match || p.startsWith(`${item.match}/`);
}

export function Sidebar() {
  const pathname = usePathname() ?? "/";
  const items = useNavItems();

  return (
    <aside className="sticky top-0 hidden h-dvh w-[232px] shrink-0 flex-col border-r border-hairline bg-plane md:flex">
      <div className="flex h-14 items-center px-4">
        <Link href={urls.overview()} className="rounded-md" aria-label="EvalCascade overview">
          <Logo />
        </Link>
      </div>
      <nav aria-label="Main" className="flex-1 overflow-y-auto px-2.5 py-2">
        <ul className="space-y-0.5">
          {items.map((item) => {
            const active = isActive(pathname, item);
            const body = (
              <>
                <item.Icon className={cn("size-4 shrink-0", active ? "text-ink" : "text-ink-3")} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{item.label}</span>
                  {item.sub && item.hint && (
                    <span className="block truncate text-2xs font-normal text-ink-3">{item.hint}</span>
                  )}
                </span>
              </>
            );
            const base = cn(
              "flex items-center gap-2.5 rounded-md px-2.5 text-[0.8125rem] font-medium",
              item.sub ? "ml-3.5 border-l border-hairline pl-3 rounded-l-none py-1" : "h-8",
            );
            return (
              <li key={item.label}>
                {item.href ? (
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      base,
                      "transition-colors",
                      active
                        ? "bg-surface text-ink shadow-[0_0_0_1px_var(--hairline)]"
                        : "text-ink-2 hover:bg-surface/70 hover:text-ink",
                    )}
                  >
                    {body}
                  </Link>
                ) : (
                  <span aria-disabled className={cn(base, "cursor-default text-ink-3/80")}>
                    {body}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="space-y-3 border-t border-hairline px-4 py-3.5">
        <ApiStatus />
        <div className="flex items-center justify-between">
          <span className="text-2xs text-ink-3">Theme</span>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}

/** Compact top bar used below the `md` breakpoint. */
export function MobileNav() {
  const pathname = usePathname() ?? "/";
  const items = useNavItems().filter((i) => !i.sub);
  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-plane/95 backdrop-blur md:hidden">
      <div className="flex h-12 items-center justify-between px-4">
        <Link href={urls.overview()} aria-label="EvalCascade overview">
          <Logo />
        </Link>
        <ThemeToggle />
      </div>
      <nav aria-label="Main" className="scroll-x flex gap-1 px-3 pb-2">
        {items.map((item) => {
          const active = isActive(pathname, item);
          return (
            <Link
              key={item.label}
              href={item.href ?? "/"}
              aria-current={active ? "page" : undefined}
              className={cn(
                "shrink-0 rounded-md px-2.5 py-1 text-xs font-medium",
                active ? "bg-surface text-ink shadow-[0_0_0_1px_var(--hairline)]" : "text-ink-2",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
