# EvalCascade dashboard

The local web dashboard for EvalCascade. It is a static Next.js export: `npm run build`
writes plain files to `web/out`, and `evalcascade serve` serves them at `/` with the API at
`/api` on the same origin. There is no Node server in production, and the dashboard sends
no telemetry and loads no external fonts or CDNs.

The API shapes live in `docs/api-contract.ts` (the source of truth). `src/lib/types.ts` is a
verbatim copy; re-copy it whenever the contract changes.

## Requirements

- Node.js 20+ (developed on 22) and npm

```bash
cd web
npm install
```

## Develop with mock data (no backend)

```bash
NEXT_PUBLIC_EVALCASCADE_MOCK=1 npm run dev
```

Open http://localhost:3000. The client answers from the typed fixtures in
`src/lib/mock/`: five synthetic experiments (three RAG runs, including a pair where
`rag-qa-prompt-v2` regresses against `rag-qa-hybrid-retriever`, and two agent runs with tool-call
traces and per-step judgments). Every fixture has `is_demo: true`, so the UI marks it DEMO
everywhere.

`NEXT_PUBLIC_EVALCASCADE_MOCK=empty` simulates a fresh install with no experiments.

Mock mode is dev-only. Without the flag, `next.config.ts` aliases the fixtures to a stub, so
they are not bundled into production output at all.

On Windows `cmd.exe`: `set "NEXT_PUBLIC_EVALCASCADE_MOCK=1" && npm run dev` (keep the quotes so
no trailing space ends up in the value). PowerShell: `$env:NEXT_PUBLIC_EVALCASCADE_MOCK="1"; npm run dev`.

## Develop against a local backend

Start the API, then point the dev server at it:

```bash
evalcascade serve                      # API on http://127.0.0.1:8000
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 npm run dev
```

The dev server runs on a different origin (port 3000), so the backend has to allow CORS from
`http://localhost:3000` in development. With `NEXT_PUBLIC_API_BASE` unset, calls go to
`/api` on the same origin, which is what production uses.

If the API is unreachable, pages show a "Cannot reach the EvalCascade API" state with the
command to start it.

### API token

When the server runs with `EVALCASCADE_API_TOKEN` set, every `/api` route except `/api/health`
and `/api/metrics` returns 401. Pages then show "This server requires an API token — add it in
Settings". Paste the token under **Settings → API token**. It is kept in this browser's
`localStorage` only, sent as `Authorization: Bearer <token>` on every request, never shown
again after saving (Replace or Clear it instead), and changing it refetches every open view.
Settings still renders without a token, and shows only what `/api/health` provides until one
is accepted.

## Build

```bash
npm run build        # static export to web/out (then scripts/normalize-export.mjs runs)
```

`output: "export"`, `trailingSlash: true` and `images.unoptimized` are set in
`next.config.ts`. Because it's a static export there are no dynamic route segments; pages read
their ids from the query string:

| Page | URL |
| --- | --- |
| Overview | `/` |
| Experiments | `/experiments/` |
| Experiment details | `/experiments/view/?id=<id>` |
| Compare and regression gate | `/compare/?baseline=<id>&candidate=<id>` |
| Case / trace | `/cases/view/?experiment=<id>&case=<case_id>` |
| Metric catalog | `/metrics/` |
| Settings | `/settings/` |

The backend should serve `out/` as static files, map directory paths to their `index.html`,
and fall back to `404.html`.

`scripts/normalize-export.mjs` runs automatically as `postbuild`. It works around a Next.js 16
static-export bug on Windows: route prefetch files come out as nested folders
(`compare/__next.compare/__PAGE__.txt`) instead of the flat names the router requests
(`compare/__next.compare.__PAGE__.txt`). On Linux and macOS it does nothing.

To preview a build without the backend, serve `out/` with any static server, for example
`python -m http.server 3000 -d out`. The pages will show the "cannot reach the API" state.

## Checks

```bash
npm run lint         # ESLint (next/core-web-vitals + TypeScript)
npm run typecheck    # next typegen && tsc --noEmit (includes the mock fixtures)
npm run build
```

## Layout

```
src/
  app/                  routes (thin server wrappers: metadata + Suspense)
  components/
    pages/              one client component per page
    shell/              sidebar, theme, API status, logo
    common/             page header, panels, KPI strip, states, DEMO badge, route and verdict badges
    charts/             routing cascade, trend (Recharts), metric deltas (Recharts),
                        histogram, confidence meter
    experiment/         metric matrix, config tabs, paginated case table
    compare/            pickers, delta table, case movers, regression gate
    case/               judgment chain, agent trace timeline, case content
    ui/                 shadcn/ui primitives (restyled)
  hooks/                useApi (race-safe fetching), stored preferences
  lib/
    types.ts            copy of docs/api-contract.ts
    api.ts              API client (bearer token, error model), mock switch
    stored.ts           safe localStorage values (API token, preferences)
    route-meta.ts       the route color system
    format.ts, urls.ts
    mock/               dev-only fixtures and a small in-memory stand-in for the backend
```

## Design notes

- Color has two jobs only: the route that produced a judgment (deterministic, Jev accepted,
  Jev to LLM, LLM direct) and the verdict (good or bad, pass or fail). Route hues are defined
  once in `globals.css` and `lib/route-meta.ts` and were checked for color-vision-deficiency
  separation. Deltas always pair color with an arrow; for cost, latency and escalation rate a
  decrease counts as good.
- Demo experiments carry a hatched DEMO badge wherever they appear. When the database has no
  real experiments, pages show a banner saying the data is synthetic.
- The "Include demo data" preference defaults to showing demo data only when there is no real
  data, so synthetic numbers never blend into real averages by default.
- Light and dark themes follow the OS by default; the sidebar toggle overrides it.
