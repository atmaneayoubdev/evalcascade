import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "cn";

export interface Crumb {
  label: string;
  href?: string;
}

export function PageHeader({
  title,
  badge,
  description,
  meta,
  actions,
  crumbs,
}: {
  title: React.ReactNode;
  badge?: React.ReactNode;
  description?: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  crumbs?: Crumb[];
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0 max-w-full">
        {crumbs && crumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="mb-1.5">
            <ol className="flex flex-wrap items-center gap-1 text-xs text-ink-3">
              {crumbs.map((c, i) => (
                <li key={`${c.label}-${i}`} className="flex items-center gap-1">
                  {i > 0 && <ChevronRight className="size-3" aria-hidden />}
                  {c.href ? (
                    <Link href={c.href} className="rounded-sm hover:text-ink">
                      {c.label}
                    </Link>
                  ) : (
                    <span className="text-ink-2">{c.label}</span>
                  )}
                </li>
              ))}
            </ol>
          </nav>
        )}
        <div className="flex flex-wrap items-center gap-2.5">
          <h1 className="min-w-0 break-words text-[1.375rem] leading-tight font-semibold tracking-[-0.018em] text-ink">
            {title}
          </h1>
          {badge}
        </div>
        {description && <p className="mt-1.5 max-w-[72ch] text-ink-2">{description}</p>}
        {meta && <div className="mt-2.5 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-ink-3">{meta}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  id,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("min-w-0 rounded-xl border border-hairline bg-surface", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 pt-3.5 pb-3">
          <div className="min-w-0">
            {title && <h2 className="text-[0.875rem] font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 max-w-[80ch] text-xs text-ink-3">{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={cn(bodyClassName)}>{children}</div>
    </section>
  );
}

/** Label/value rows used by config panels. */
export function KeyValues({
  items,
  className,
}: {
  items: { label: React.ReactNode; value: React.ReactNode; mono?: boolean }[];
  className?: string;
}) {
  return (
    <dl className={cn("divide-y divide-hairline", className)}>
      {items.map((it, i) => (
        <div key={i} className="grid grid-cols-[minmax(8rem,40%)_1fr] gap-3 px-4 py-2 text-[0.8125rem]">
          <dt className="text-ink-3">{it.label}</dt>
          <dd className={cn("min-w-0 break-words text-ink", it.mono && "font-mono text-xs leading-5")}>{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SectionTitle({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="mt-9 mb-3 flex flex-wrap items-end justify-between gap-3 first:mt-0">
      <h2 className="text-[0.9375rem] font-semibold tracking-[-0.01em] text-ink">{children}</h2>
      {aside}
    </div>
  );
}
