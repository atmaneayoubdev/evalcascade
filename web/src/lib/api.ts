/**
 * EvalCascade API client. Every call goes to `${NEXT_PUBLIC_API_BASE}/api/...`
 * (default: same origin, which is how `evalcascade serve` hosts the dashboard).
 *
 * Dev-only mock mode: with NEXT_PUBLIC_EVALCASCADE_MOCK=1 the client answers from
 * the fixtures in `./mock` instead of the network (`=empty` simulates a fresh
 * install with no experiments). The mock module is loaded lazily, so it never
 * ships in the main bundle and production builds without the flag never use it.
 */
import type {
  CaseResult,
  CaseResultRow,
  Comparison,
  ConfigSummary,
  Experiment,
  ExperimentListItem,
  GateRequest,
  GateResult,
  Health,
  MetricInfo,
  Overview,
  Page,
} from "./types";
import { apiToken } from "./stored";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/+$/, "");

const MOCK_FLAG = process.env.NEXT_PUBLIC_EVALCASCADE_MOCK ?? "";
export const MOCK_MODE: false | "demo" | "empty" =
  MOCK_FLAG === "1" || MOCK_FLAG === "true" ? "demo" : MOCK_FLAG === "empty" ? "empty" : false;

export type CaseFilter = "all" | "passed" | "failed" | "escalated";

export type ApiErrorKind = "network" | "not_found" | "unauthorized" | "http" | "invalid";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly detail: string | null;
  readonly path: string;
  /** whether the failed request carried an API token (tells "add a token" from "token rejected") */
  readonly tokenSent: boolean;

  constructor(
    kind: ApiErrorKind,
    path: string,
    opts: { status?: number; detail?: string; tokenSent?: boolean } = {},
  ) {
    super(opts.detail ?? `${kind} error for ${path}`);
    this.name = "ApiError";
    this.kind = kind;
    this.path = path;
    this.status = opts.status ?? null;
    this.detail = opts.detail ?? null;
    this.tokenSent = opts.tokenSent ?? false;
  }
}

export function toApiError(err: unknown, path = ""): ApiError {
  if (err instanceof ApiError) return err;
  if (err instanceof Error) return new ApiError("invalid", path, { detail: err.message });
  return new ApiError("invalid", path, { detail: String(err) });
}

export interface ApiClient {
  health(): Promise<Health>;
  config(): Promise<ConfigSummary>;
  overview(includeDemo: boolean): Promise<Overview>;
  metrics(): Promise<MetricInfo[]>;
  experiments(opts?: { includeDemo?: boolean; limit?: number }): Promise<ExperimentListItem[]>;
  experiment(id: string): Promise<Experiment>;
  cases(
    id: string,
    opts?: { limit?: number; offset?: number; filter?: CaseFilter },
  ): Promise<Page<CaseResultRow>>;
  caseResult(id: string, caseId: string): Promise<CaseResult>;
  compare(baseline: string, candidate: string): Promise<Comparison>;
  gate(req: GateRequest): Promise<GateResult>;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

const enc = encodeURIComponent;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}/api${path}`;
  // Servers started with EVALCASCADE_API_TOKEN require it on every route except
  // /api/health and /api/metrics. Sending it everywhere is harmless.
  const token = apiToken.get().trim();
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch {
    // fetch only rejects when the request never got a response: server down, DNS, CORS.
    throw new ApiError("network", path);
  }

  const isJson = (res.headers.get("content-type") ?? "").includes("json");

  if (!res.ok) {
    let detail: string | undefined;
    if (isJson) {
      try {
        const body = (await res.json()) as { detail?: unknown };
        if (typeof body.detail === "string") detail = body.detail;
        else if (body.detail !== undefined) detail = JSON.stringify(body.detail);
      } catch {
        /* ignore malformed error bodies */
      }
    }
    // A non-JSON 404 means nothing is answering under /api (e.g. the Next dev
    // server without a backend), which is the "API not running" case.
    if (res.status === 404 && !isJson) throw new ApiError("network", path, { status: 404 });
    if (res.status === 404) throw new ApiError("not_found", path, { status: 404, detail });
    if (res.status === 401 || res.status === 403)
      throw new ApiError("unauthorized", path, { status: res.status, detail, tokenSent: Boolean(token) });
    throw new ApiError("http", path, { status: res.status, detail: detail ?? res.statusText });
  }

  if (!isJson) throw new ApiError("network", path, { status: res.status });
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError("invalid", path, { detail: "The API returned malformed JSON." });
  }
}

const httpClient: ApiClient = {
  health: () => request<Health>("/health"),
  config: () => request<ConfigSummary>("/config"),
  overview: (includeDemo) => request<Overview>(`/overview${query({ include_demo: includeDemo })}`),
  metrics: () => request<MetricInfo[]>("/metrics"),
  experiments: (opts = {}) =>
    request<ExperimentListItem[]>(
      `/experiments${query({ include_demo: opts.includeDemo ?? true, limit: opts.limit })}`,
    ),
  experiment: (id) => request<Experiment>(`/experiments/${enc(id)}`),
  cases: (id, opts = {}) =>
    request<Page<CaseResultRow>>(
      `/experiments/${enc(id)}/cases${query({
        limit: opts.limit,
        offset: opts.offset,
        filter: opts.filter && opts.filter !== "all" ? opts.filter : undefined,
      })}`,
    ),
  caseResult: (id, caseId) =>
    request<CaseResult>(`/experiments/${enc(id)}/cases/${enc(caseId)}`),
  compare: (baseline, candidate) =>
    request<Comparison>(`/compare${query({ baseline, candidate })}`),
  gate: (req) =>
    request<GateResult>("/gate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
};

let mockClient: Promise<ApiClient> | null = null;

function client(): Promise<ApiClient> {
  // Compared against the inlined env value directly so production builds without
  // the flag dead-code-eliminate the import and never emit the fixture chunk.
  if (
    process.env.NEXT_PUBLIC_EVALCASCADE_MOCK === "1" ||
    process.env.NEXT_PUBLIC_EVALCASCADE_MOCK === "true" ||
    process.env.NEXT_PUBLIC_EVALCASCADE_MOCK === "empty"
  ) {
    const variant = MOCK_MODE || "demo";
    mockClient ??= import("@/lib/mock").then((m) => m.createMockClient(variant));
    return mockClient;
  }
  return Promise.resolve(httpClient);
}

/** The API surface the app uses. Resolves to the HTTP client or, in mock mode, the fixtures. */
export const api: ApiClient = {
  health: () => client().then((c) => c.health()),
  config: () => client().then((c) => c.config()),
  overview: (includeDemo) => client().then((c) => c.overview(includeDemo)),
  metrics: () => client().then((c) => c.metrics()),
  experiments: (opts) => client().then((c) => c.experiments(opts)),
  experiment: (id) => client().then((c) => c.experiment(id)),
  cases: (id, opts) => client().then((c) => c.cases(id, opts)),
  caseResult: (id, caseId) => client().then((c) => c.caseResult(id, caseId)),
  compare: (b, c2) => client().then((c) => c.compare(b, c2)),
  gate: (req) => client().then((c) => c.gate(req)),
};
