"use client";

import Link from "next/link";
import { FileQuestion, KeyRound, PlugZap, RotateCw, TriangleAlert } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { API_BASE, type ApiError } from "@/lib/api";
import { Cmd, CommandLine } from "./code";

function StateFrame({
  icon,
  title,
  children,
  className,
  actions,
}: {
  icon: React.ReactNode;
  title: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-xl border border-hairline bg-surface px-6 py-10 sm:px-10", className)}>
      <div className="mx-auto flex max-w-[34rem] flex-col items-start gap-3">
        <div className="grid size-9 place-items-center rounded-lg border border-hairline bg-sunken text-ink-2">{icon}</div>
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {children && <div className="space-y-3 text-[0.8125rem] text-ink-2">{children}</div>}
        {actions && <div className="mt-1 flex flex-wrap gap-2">{actions}</div>}
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: ApiError; onRetry?: () => void; className?: string }) {
  const retry = onRetry && (
    <Button variant="outline" size="sm" onClick={onRetry}>
      <RotateCw aria-hidden />
      Retry
    </Button>
  );

  if (error.kind === "network") {
    const where = `${API_BASE || (typeof window !== "undefined" ? window.location.origin : "")}/api`;
    return (
      <StateFrame
        className={className}
        icon={<PlugZap className="size-4.5" aria-hidden />}
        title={
          <>
            Cannot reach the EvalCascade API — run <Cmd>evalcascade serve</Cmd>
          </>
        }
        actions={retry}
      >
        <p>
          The dashboard reads everything from the local API, which was not reachable at <span className="font-mono text-xs text-ink">{where}</span>.
          Start it and retry:
        </p>
        <CommandLine command="evalcascade serve" />
        <p className="text-xs text-ink-3">
          Running the dashboard with <span className="font-mono">npm run dev</span>? Point it at the server with{" "}
          <span className="font-mono">NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000</span>, or use mock mode.
        </p>
      </StateFrame>
    );
  }
  if (error.kind === "not_found") {
    return <NotFoundState className={className} detail={error.detail} />;
  }
  if (error.kind === "unauthorized") {
    return <TokenRequiredState tokenSent={error.tokenSent} className={className} onRetry={onRetry} />;
  }
  return (
    <StateFrame
      className={className}
      icon={<TriangleAlert className="size-4.5" aria-hidden />}
      title={error.kind === "invalid" ? "The API sent a response the dashboard can't read" : `The API returned an error${error.status ? ` (${error.status})` : ""}`}
      actions={retry}
    >
      {error.detail && <p className="font-mono text-xs break-words text-ink">{error.detail}</p>}
      <p className="text-xs text-ink-3">Check the server log for details. Request: {error.path}</p>
    </StateFrame>
  );
}

/** 401/403: the server was started with EVALCASCADE_API_TOKEN. */
export function TokenRequiredState({
  tokenSent,
  className,
  onRetry,
}: {
  tokenSent: boolean;
  className?: string;
  onRetry?: () => void;
}) {
  return (
    <StateFrame
      className={className}
      icon={<KeyRound className="size-4.5" aria-hidden />}
      title={
        tokenSent
          ? "The saved API token was rejected — update it in Settings"
          : "This server requires an API token — add it in Settings"
      }
      actions={
        <>
          <Button asChild size="sm">
            <Link href="/settings/#api-token">
              <KeyRound aria-hidden />
              {tokenSent ? "Update API token" : "Add API token"}
            </Link>
          </Button>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RotateCw aria-hidden />
              Retry
            </Button>
          )}
        </>
      }
    >
      <p>
        {tokenSent
          ? "The server refused the token stored in this browser. Paste the current value of EVALCASCADE_API_TOKEN."
          : "The server was started with EVALCASCADE_API_TOKEN set, so every request needs that token. It is stored only in this browser."}
      </p>
    </StateFrame>
  );
}

export function NotFoundState({ detail, className, what = "This page" }: { detail?: string | null; className?: string; what?: string }) {
  return (
    <StateFrame
      className={className}
      icon={<FileQuestion className="size-4.5" aria-hidden />}
      title={`${what} doesn't exist`}
      actions={
        <Button asChild variant="outline" size="sm">
          <Link href="/experiments/">Browse experiments</Link>
        </Button>
      }
    >
      <p>{detail ?? "It may have been deleted, or the link is incomplete."}</p>
    </StateFrame>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  actions,
  className,
}: {
  icon: React.ReactNode;
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <StateFrame className={className} icon={icon} title={title} actions={actions}>
      {children}
    </StateFrame>
  );
}

/** Shown when the database holds no experiments at all. */
export function NoExperiments({ className }: { className?: string }) {
  return (
    <div className={cn("rounded-xl border border-hairline bg-surface px-6 py-10 sm:px-10", className)}>
      <div className="mx-auto max-w-[36rem]">
        <svg viewBox="0 0 120 44" aria-hidden className="mb-5 h-11 w-[120px]">
          <rect x="2" y="3" width="44" height="9" rx="2.5" fill="var(--route-det)" opacity="0.9" />
          <rect x="30" y="17.5" width="44" height="9" rx="2.5" fill="var(--route-jev)" opacity="0.9" />
          <rect x="58" y="32" width="44" height="9" rx="2.5" fill="var(--route-llm)" opacity="0.9" />
        </svg>
        <h2 className="text-base font-semibold text-ink">No experiments yet</h2>
        <p className="mt-1.5 text-[0.8125rem] text-ink-2">
          An experiment is one run of a metric suite over a dataset. Record one and it shows up here, with scores, costs and
          which judge decided each metric.
        </p>
        <div className="mt-5 space-y-4">
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-2">See the dashboard with sample data</p>
            <CommandLine command="evalcascade demo" />
            <p className="mt-1 text-xs text-ink-3">Seeds synthetic experiments. They are marked DEMO everywhere.</p>
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-2">Record a real evaluation</p>
            <div className="space-y-1.5">
              <CommandLine command="evalcascade init" />
              <CommandLine command="evalcascade run datasets/rag_qa.jsonl --suite rag --name baseline" />
            </div>
            <p className="mt-1 text-xs text-ink-3">
              <span className="font-mono">init</span> creates <span className="font-mono">evalcascade.toml</span> and copies the sample
              datasets into <span className="font-mono">./datasets</span>. Real runs call Jev, so set{" "}
              <span className="font-mono">OPENROUTER_API_KEY</span> first.
            </p>
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-ink-2">Or skip setup and use the built-in sample</p>
            <CommandLine command="evalcascade run sample:rag_qa --suite rag" />
          </div>
        </div>
      </div>
    </div>
  );
}

export function PageSkeleton({ kpis = 4, panels = 2 }: { kpis?: number; panels?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading">
      <Skeleton className="mb-2 h-3 w-24" />
      <Skeleton className="mb-7 h-7 w-72" />
      <div className="mb-6 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-hairline bg-hairline sm:grid-cols-4">
        {Array.from({ length: kpis }).map((_, i) => (
          <div key={i} className="bg-surface px-4 py-3.5">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="mt-2.5 h-6 w-16" />
          </div>
        ))}
      </div>
      <div className="space-y-6">
        {Array.from({ length: panels }).map((_, i) => (
          <Skeleton key={i} className="h-56 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}

export function InlineLoading({ className, rows = 5 }: { className?: string; rows?: number }) {
  return (
    <div className={cn("space-y-2 p-4", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-7 w-full" />
      ))}
    </div>
  );
}
