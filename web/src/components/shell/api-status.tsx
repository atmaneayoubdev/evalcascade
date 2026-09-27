"use client";

import { useEffect } from "react";
import { cn } from "cn";
import { api, API_BASE, MOCK_MODE } from "@/lib/api";
import { useApi } from "@/hooks/use-api";

/** Small connection indicator in the sidebar footer. Re-checks when the tab regains focus. */
export function ApiStatus() {
  const { data, error, loading, reload } = useApi("health", () => api.health());

  useEffect(() => {
    const onFocus = () => reload();
    window.addEventListener("focus", onFocus);
    const t = window.setInterval(reload, 60_000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(t);
    };
  }, [reload]);

  let tone: "ok" | "warn" | "bad" | "idle" = "idle";
  let label = "Checking API…";
  let detail: string | null = API_BASE || null;
  if (MOCK_MODE) {
    tone = "warn";
    label = MOCK_MODE === "empty" ? "Mock mode (empty)" : "Mock mode";
    detail = "Fixtures, no backend";
  } else if (data) {
    tone = data.status === "ok" && data.database === "ok" ? "ok" : "warn";
    label = tone === "ok" ? "API connected" : "API degraded";
    detail = `v${data.version}${data.database !== "ok" ? ", database error" : ""}`;
  } else if (error) {
    tone = "bad";
    label = "API unreachable";
    detail = "Run evalcascade serve";
  } else if (loading) {
    tone = "idle";
  }

  return (
    <div className="flex min-w-0 items-center gap-2 text-xs" role="status" aria-live="polite">
      <span
        aria-hidden
        className={cn(
          "size-2 shrink-0 rounded-full",
          tone === "ok" && "bg-good",
          tone === "warn" && "bg-route-esc",
          tone === "bad" && "bg-bad",
          tone === "idle" && "bg-route-none",
        )}
      />
      <span className="min-w-0">
        <span className="block truncate font-medium text-ink-2">{label}</span>
        {detail && <span className="block truncate text-ink-3">{detail}</span>}
      </span>
    </div>
  );
}
