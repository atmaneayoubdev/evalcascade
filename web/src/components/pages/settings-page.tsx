"use client";

import { useId, useState } from "react";
import { Check, CircleAlert, KeyRound, Lock, X } from "lucide-react";
import { cn } from "cn";
import { Cmd } from "@/components/common/code";
import { KeyValues, PageHeader, Panel } from "@/components/common/layout";
import { RouteLegend } from "@/components/common/route";
import { ErrorState, PageSkeleton } from "@/components/common/states";
import { PolicyOverrides, PolicyValues } from "@/components/experiment/config-panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { apiToken, useStored } from "@/hooks/use-stored";
import { api, API_BASE, MOCK_MODE, type ApiError } from "@/lib/api";
import type { ConfigSummary, Health } from "@/lib/types";

function Configured({ ok, what }: { ok: boolean; what: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[0.8125rem] font-medium", ok ? "text-good-ink" : "text-bad-ink")}>
      <span
        className="grid size-4 place-items-center rounded-full"
        style={{ background: `color-mix(in oklab, var(${ok ? "--good" : "--bad"}) 16%, var(--surface))` }}
        aria-hidden
      >
        {ok ? <Check className="size-3" /> : <X className="size-3" />}
      </span>
      <span className="sr-only">{what}: </span>
      {ok ? "Configured" : "Not configured"}
    </span>
  );
}

/** A fixed-width mask: it reveals neither the token nor its length. */
const MASK = "••••••••••••";

/**
 * API token for servers started with EVALCASCADE_API_TOKEN. The saved token is
 * never rendered back: the page only shows that one is set.
 */
function ApiTokenPanel({ configState, config }: { configState: ApiError | undefined; config: ConfigSummary | undefined }) {
  const [saved, setSaved] = useStored(apiToken);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const inputId = useId();
  const hasToken = saved.trim().length > 0;
  const showForm = !hasToken || editing;
  const rejected = configState?.kind === "unauthorized";

  const save = () => {
    const value = draft.trim();
    if (!value) return;
    setSaved(value);
    setDraft("");
    setEditing(false);
  };

  let status: { tone: "good" | "bad" | "neutral"; text: string } | null = null;
  if (rejected) {
    status = hasToken
      ? { tone: "bad", text: "The server rejected the saved token." }
      : { tone: "bad", text: "This server requires a token. Nothing loads until one is added." };
  } else if (config) {
    status = hasToken
      ? { tone: "good", text: "Token accepted." }
      : config.api_auth_enabled
        ? { tone: "neutral", text: "Authentication is enabled on this server." }
        : { tone: "neutral", text: "This server doesn't require a token." };
  }

  return (
    <Panel
      id="api-token"
      className="scroll-mt-6"
      title="API token"
      description="Only needed when the server was started with EVALCASCADE_API_TOKEN. Stored in this browser only and sent as a bearer token on every API request."
    >
      <div className="space-y-3 border-t border-hairline px-4 py-3.5">
        {hasToken && !editing && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="grid size-7 place-items-center rounded-md border border-hairline bg-sunken text-ink-2" aria-hidden>
                <Lock className="size-3.5" />
              </span>
              <div className="min-w-0">
                <div className="text-[0.8125rem] font-medium text-ink">Token saved</div>
                <div className="font-mono text-xs tracking-wider text-ink-3" aria-label="Token hidden">
                  {MASK}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                Replace
              </Button>
              <Button variant="outline" size="sm" onClick={() => setSaved("")}>
                <X aria-hidden />
                Clear
              </Button>
            </div>
          </div>
        )}

        {showForm && (
          <form
            className="flex flex-col gap-2 sm:flex-row sm:items-end"
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
          >
            <div className="min-w-0 flex-1">
              <label htmlFor={inputId} className="mb-1 block text-xs font-medium text-ink-2">
                {hasToken ? "New token" : "Token"}
              </label>
              <Input
                id={inputId}
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Paste the value of EVALCASCADE_API_TOKEN"
                className="h-8 bg-surface font-mono text-[0.8125rem]"
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={!draft.trim()} className="h-8">
                <KeyRound aria-hidden />
                Save token
              </Button>
              {hasToken && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-8"
                  onClick={() => {
                    setDraft("");
                    setEditing(false);
                  }}
                >
                  Cancel
                </Button>
              )}
            </div>
          </form>
        )}

        {status && (
          <p
            role="status"
            className={cn(
              "flex items-center gap-1.5 text-xs",
              status.tone === "good" && "text-good-ink",
              status.tone === "bad" && "text-bad-ink",
              status.tone === "neutral" && "text-ink-3",
            )}
          >
            {status.tone === "good" ? (
              <Check className="size-3.5" aria-hidden />
            ) : status.tone === "bad" ? (
              <CircleAlert className="size-3.5" aria-hidden />
            ) : null}
            {status.text}
          </p>
        )}
      </div>
    </Panel>
  );
}

function RoutingExplainer({ c }: { c: ConfigSummary | undefined }) {
  const model = (m: string | undefined, fallback: string) =>
    m ? <span className="font-mono text-xs">{m}</span> : <>{fallback}</>;
  const steps = [
    {
      color: "var(--route-det)",
      ink: "var(--route-det-ink)",
      title: "Rules first",
      body: (
        <>
          When a metric has a deterministic check (exact match, JSON Schema validation, duplicate-call detection) and the check can decide,
          that is the verdict. No model call, no cost.
        </>
      ),
    },
    {
      color: "var(--route-jev)",
      ink: "var(--route-jev-ink)",
      title: "Jev decides",
      body: (
        <>
          Otherwise the metric&apos;s questions go to Jev, TypeSafe&apos;s System One decision model ({model(c?.jev.model, "the configured Jev model")} via
          OpenRouter). It returns calibrated probabilities and a confidence in a few hundred milliseconds.
        </>
      ),
    },
    {
      color: "var(--route-esc)",
      ink: "var(--route-esc-ink)",
      title: "Escalate only when unsure",
      body: (
        <>
          If Jev&apos;s confidence is below <Cmd>escalate_below</Cmd>
          {c ? (
            <>
              {" "}
              (currently {c.policy.escalate_below.toFixed(2)}
              {Object.keys(c.policy.overrides).length > 0 && ", with per-metric overrides"})
              {c.policy.escalate_on_error && ", or the Jev call fails"}
            </>
          ) : (
            " (0.82 by default), or the Jev call fails"
          )}
          , the LLM judge ({model(c?.judge.model, "the configured judge model")}) makes the final call and writes an explanation.
        </>
      ),
    },
    {
      color: "var(--route-llm)",
      ink: "var(--route-llm-ink)",
      title: "Reasoning goes straight to the LLM",
      body:
        !c || c.policy.route_reasoning_to_fallback ? (
          <>Metrics marked as requiring multi-step reasoning skip Jev and go directly to the LLM judge.</>
        ) : (
          <>Disabled on this server: reasoning metrics also start with Jev.</>
        ),
    },
  ];
  return (
    <Panel title="How routing works" description="System One judges first; LLMs only when necessary." bodyClassName="px-4 pb-4">
      <ol className="space-y-0">
        {steps.map((s, i) => (
          <li key={s.title} className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-3 pb-4 last:pb-0">
            {i < steps.length - 1 && <span aria-hidden className="absolute top-7 bottom-0 left-3.5 w-px -translate-x-1/2 bg-hairline-strong" />}
            <span
              className="tabular relative z-10 grid size-7 place-items-center rounded-full text-xs font-semibold"
              style={{
                color: s.ink,
                background: `color-mix(in oklab, ${s.color} 16%, var(--surface))`,
                boxShadow: `inset 0 0 0 1.5px ${s.color}`,
              }}
              aria-hidden
            >
              {i + 1}
            </span>
            <div className="pt-0.5">
              <h3 className="text-[0.8125rem] font-semibold text-ink">{s.title}</h3>
              <p className="mt-0.5 max-w-[70ch] text-[0.8125rem] leading-relaxed text-ink-2">{s.body}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-4 border-t border-hairline pt-3">
        <p className="mb-2 text-xs text-ink-3">Every metric result records the route that produced it:</p>
        <RouteLegend includeNone />
      </div>
    </Panel>
  );
}

function ServerPanel({ c, health, healthError }: { c: ConfigSummary | undefined; health: Health | undefined; healthError: boolean }) {
  const items: { label: string; value: React.ReactNode; mono?: boolean }[] = [
    { label: "EvalCascade version", value: c?.version ?? health?.version ?? "—", mono: true },
  ];
  if (c) items.push({ label: "Database", value: c.database, mono: true });
  items.push({
    label: "Health",
    value: health
      ? `${health.status === "ok" ? "OK" : "Degraded"} (database ${health.database})`
      : healthError
        ? "Unreachable"
        : "Checking…",
  });
  if (c) items.push({ label: "API authentication", value: c.api_auth_enabled ? "Enabled" : "Disabled" });
  items.push({ label: "Dashboard API base", value: MOCK_MODE ? "Mock fixtures (dev only)" : `${API_BASE || "same origin"}/api`, mono: true });
  return (
    <Panel title="Server">
      <KeyValues className="border-t border-hairline" items={items} />
    </Panel>
  );
}

export function SettingsPage() {
  const cfg = useApi("config", () => api.config());
  const health = useApi("health", () => api.health());
  const c = cfg.data;
  const unauthorized = cfg.error?.kind === "unauthorized";

  const header = (
    <PageHeader
      title="Settings"
      description={
        <>
          Summary of the server configuration. Change it in <Cmd>evalcascade.toml</Cmd> or the environment and restart{" "}
          <Cmd>evalcascade serve</Cmd>.
        </>
      }
    />
  );

  // A hard failure (server down, 5xx) has nothing to degrade to except the token form.
  if (cfg.error && !unauthorized) {
    return (
      <>
        {header}
        <ErrorState error={cfg.error} onRetry={cfg.reload} />
        <div className="mt-6 max-w-3xl">
          <ApiTokenPanel configState={cfg.error} config={undefined} />
        </div>
      </>
    );
  }
  if (!c && !unauthorized) return <PageSkeleton kpis={0} panels={3} />;

  return (
    <>
      {header}
      <div className="grid items-start gap-6 xl:grid-cols-2">
        <div className="grid gap-6">
          <ApiTokenPanel configState={cfg.error} config={c} />
          <ServerPanel c={c} health={health.data} healthError={Boolean(health.error)} />
          {c ? (
            <>
              <Panel title="Credentials" description="Only whether a key is set. Secrets never leave the server.">
                <KeyValues
                  className="border-t border-hairline"
                  items={[
                    { label: "OpenRouter API key (Jev)", value: <Configured ok={c.openrouter_api_key_configured} what="OpenRouter API key" /> },
                    { label: "LLM judge API key", value: <Configured ok={c.judge_api_key_configured} what="LLM judge API key" /> },
                  ]}
                />
              </Panel>
              <Panel title="Jev (System One)">
                <KeyValues
                  className="border-t border-hairline"
                  items={[
                    { label: "Model", value: c.jev.model, mono: true },
                    { label: "Surface", value: c.jev.surface, mono: true },
                    { label: "Base URL", value: c.jev.base_url, mono: true },
                    { label: "Timeout", value: `${c.jev.timeout_s} s` },
                    { label: "Max retries", value: c.jev.max_retries },
                  ]}
                />
              </Panel>
              <Panel title="LLM judge">
                <KeyValues
                  className="border-t border-hairline"
                  items={[
                    { label: "Provider", value: c.judge.provider, mono: true },
                    { label: "Model", value: c.judge.model, mono: true },
                    { label: "Base URL", value: c.judge.base_url, mono: true },
                    { label: "Timeout", value: `${c.judge.timeout_s} s` },
                    { label: "Temperature", value: c.judge.temperature },
                  ]}
                />
              </Panel>
            </>
          ) : (
            <Panel title="Configuration" description="Credentials, models and routing policy appear here once the server accepts the token.">
              <div className="border-t border-hairline px-4 py-3 text-xs text-ink-3">Hidden: the server requires an API token.</div>
            </Panel>
          )}
        </div>
        <div className="grid gap-6">
          <RoutingExplainer c={c} />
          {c && (
            <Panel title="Routing policy" description="Defaults applied to every run unless overridden.">
              <div className="border-t border-hairline">
                <PolicyValues policy={c.policy} />
              </div>
              <h3 className="border-t border-hairline bg-sunken/60 px-4 py-2 text-xs font-medium text-ink-2">Per-metric overrides</h3>
              <PolicyOverrides overrides={c.policy.overrides} />
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
