"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "cn";

export function Cmd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <code
      className={cn(
        "rounded-[4px] border border-hairline bg-sunken px-1.5 py-px font-mono text-[0.8em] whitespace-nowrap text-ink",
        className,
      )}
    >
      {children}
    </code>
  );
}

export function CopyButton({ text, label = "Copy", className }: { text: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1400);
        } catch {
          /* clipboard unavailable (http origin); nothing to do */
        }
      }}
      className={cn("grid size-6 place-items-center rounded-md text-ink-3 hover:bg-sunken hover:text-ink", className)}
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
    >
      {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
    </button>
  );
}

/** A shell command on its own line, with a copy button. */
export function CommandLine({ command, className }: { command: string; className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-lg border border-hairline bg-sunken py-1.5 pr-1.5 pl-3 font-mono text-xs text-ink",
        className,
      )}
    >
      <span className="min-w-0 truncate">
        <span aria-hidden className="mr-2 text-ink-3 select-none">
          $
        </span>
        {command}
      </span>
      <CopyButton text={command} label="Copy command" />
    </div>
  );
}

export function JsonBlock({
  value,
  className,
  maxHeight = 320,
}: {
  value: unknown;
  className?: string;
  maxHeight?: number;
}) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <pre
      className={cn(
        "overflow-auto rounded-lg border border-hairline bg-sunken px-3 py-2.5 font-mono text-xs leading-5 whitespace-pre text-ink",
        className,
      )}
      style={{ maxHeight }}
    >
      {text}
    </pre>
  );
}
