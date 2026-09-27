import { cn } from "cn";

/**
 * The mark is the product: three judges stepping down the cascade.
 * Deterministic, then Jev, then the LLM judge, each only when the one above
 * could not decide.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden className={cn("size-5 shrink-0", className)}>
      <rect x="1.5" y="2.5" width="9" height="4" rx="1.25" fill="var(--route-det)" />
      <rect x="5.5" y="8" width="9" height="4" rx="1.25" fill="var(--route-jev)" />
      <rect x="9.5" y="13.5" width="9" height="4" rx="1.25" fill="var(--route-llm)" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <LogoMark />
      <span className="text-[0.95rem] font-semibold tracking-[-0.015em] text-ink">EvalCascade</span>
    </span>
  );
}
