"use client";

import { useCallback, useEffect, useEffectEvent, useState, useSyncExternalStore } from "react";
import { toApiError, type ApiError } from "@/lib/api";
import { apiToken, tokenFingerprint } from "@/lib/stored";

export interface ApiState<T> {
  data: T | undefined;
  error: ApiError | undefined;
  loading: boolean;
  /** last successful value, kept while a new key loads (for pagination etc.) */
  previous: T | undefined;
  reload: () => void;
}

/**
 * Fetches `fetcher()` whenever `key` changes. `key = null` pauses the request.
 * Responses for stale keys are dropped, so fast navigation never shows old data.
 * Changing the API token (in Settings) refetches every active query.
 */
export function useApi<T>(key: string | null, fetcher: () => Promise<T>): ApiState<T> {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<{ key: string; data?: T; error?: ApiError } | null>(null);
  const [previous, setPrevious] = useState<T | undefined>(undefined);
  const run = useEffectEvent(fetcher);
  const token = useSyncExternalStore(apiToken.subscribe, apiToken.get, () => apiToken.fallback);
  const fullKey = key === null ? null : `${key}#${nonce}#${tokenFingerprint(token)}`;

  useEffect(() => {
    if (fullKey === null) return;
    let active = true;
    run().then(
      (data) => {
        if (!active) return;
        setState({ key: fullKey, data });
        setPrevious(data);
      },
      (err: unknown) => {
        if (active) setState({ key: fullKey, error: toApiError(err) });
      },
    );
    return () => {
      active = false;
    };
  }, [fullKey]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const settled = state !== null && state.key === fullKey;
  return {
    data: settled ? state.data : undefined,
    error: settled ? state.error : undefined,
    loading: fullKey !== null && !settled,
    previous,
    reload,
  };
}
