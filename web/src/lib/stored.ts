/**
 * A string value persisted in web storage and shared by everything that reads it.
 * Every storage access is wrapped: private windows, blocked storage and SSR all
 * fall back to the default instead of throwing.
 */
export interface StoredValue<T extends string> {
  get: () => T;
  set: (v: T) => void;
  subscribe: (listener: () => void) => () => void;
  fallback: T;
}

export function storedValue<T extends string>(
  key: string,
  fallback: T,
  area: "local" | "session" = "local",
): StoredValue<T> {
  const listeners = new Set<() => void>();
  const storage = (): Storage | null => {
    try {
      if (typeof window === "undefined") return null;
      return area === "local" ? window.localStorage : window.sessionStorage;
    } catch {
      return null;
    }
  };
  const get = (): T => {
    try {
      return (storage()?.getItem(key) as T | null) ?? fallback;
    } catch {
      return fallback;
    }
  };
  const set = (v: T) => {
    try {
      const s = storage();
      if (v === fallback) s?.removeItem(key);
      else s?.setItem(key, v);
    } catch {
      /* storage blocked: the change still reaches current listeners below */
    }
    listeners.forEach((l) => l());
  };
  const subscribe = (listener: () => void) => {
    listeners.add(listener);
    const onStorage = (e: StorageEvent) => {
      if (e.key === key) listener();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  };
  return { get, set, subscribe, fallback };
}

/**
 * Bearer token for servers started with EVALCASCADE_API_TOKEN. Kept in this
 * browser's localStorage only; the UI never displays it after saving.
 */
export const apiToken = storedValue<string>("evalcascade.apiToken", "");

/** Short, non-reversible fingerprint so caches can key on "which token" without holding it. */
export function tokenFingerprint(token: string): string {
  if (!token) return "none";
  let h = 0x811c9dc5;
  for (let i = 0; i < token.length; i++) {
    h ^= token.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(36);
}
