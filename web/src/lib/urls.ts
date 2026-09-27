/**
 * App URLs. The dashboard is a static export, so there are no dynamic route
 * segments: everything that varies travels in the query string. Paths keep the
 * trailing slash that `trailingSlash: true` produces, so links never rely on a
 * server-side redirect.
 */

function withQuery(path: string, params: Record<string, string | number | null | undefined>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}

export const urls = {
  overview: () => "/",
  experiments: () => "/experiments/",
  experiment: (id: string, extra: { filter?: string; page?: number } = {}) =>
    withQuery("/experiments/view/", { id, filter: extra.filter, page: extra.page }),
  compare: (baseline?: string | null, candidate?: string | null) =>
    withQuery("/compare/", { baseline, candidate }),
  caseView: (experiment: string, caseId: string) =>
    withQuery("/cases/view/", { experiment, case: caseId }),
  metrics: () => "/metrics/",
  settings: () => "/settings/",
};
