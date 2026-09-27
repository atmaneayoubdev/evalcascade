/**
 * Stand-in for the mock client in builds without NEXT_PUBLIC_EVALCASCADE_MOCK.
 * next.config.ts aliases `@/lib/mock` here so demo fixtures never ship in
 * production output. It is unreachable at runtime (api.ts only imports the
 * mock module when the flag is set).
 */
import type { ApiClient } from "../api";

export function createMockClient(variant: "demo" | "empty"): ApiClient {
  void variant;
  throw new Error("Mock mode is not enabled in this build. Set NEXT_PUBLIC_EVALCASCADE_MOCK=1 and rebuild.");
}
