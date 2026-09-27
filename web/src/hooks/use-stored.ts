"use client";

import { useSyncExternalStore } from "react";
import { storedValue, type StoredValue } from "@/lib/stored";

export { apiToken } from "@/lib/stored";

export function useStored<T extends string>(v: StoredValue<T>): [T, (next: T) => void] {
  const value = useSyncExternalStore(v.subscribe, v.get, () => v.fallback);
  return [value, v.set];
}

// ---------------------------------------------------------------------------
// App preferences
// ---------------------------------------------------------------------------

export type DemoPreference = "auto" | "show" | "hide";
/** "auto" = show demo data only when there is no real data. */
export const demoPreference = storedValue<DemoPreference>("evalcascade.demo", "auto");

export type ThemePreference = "system" | "light" | "dark";
export const themePreference = storedValue<ThemePreference>("evalcascade.theme", "system");

/** Last experiment / case the user opened, for the contextual sidebar links. */
export const recentExperiment = storedValue<string>("evalcascade.recent.experiment", "", "session");
export const recentCase = storedValue<string>("evalcascade.recent.case", "", "session");

export function resolveDemo(pref: DemoPreference, hasRealData: boolean): boolean {
  if (pref === "show") return true;
  if (pref === "hide") return false;
  return !hasRealData;
}
