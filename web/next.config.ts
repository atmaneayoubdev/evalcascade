import type { NextConfig } from "next";

// The dashboard never phones home. Opt this project out of Next.js' anonymous
// build/dev telemetry (read by Next after the config is loaded).
process.env.NEXT_TELEMETRY_DISABLED ??= "1";

const mockFlag = process.env.NEXT_PUBLIC_EVALCASCADE_MOCK ?? "";
const mockEnabled = mockFlag === "1" || mockFlag === "true" || mockFlag === "empty";

const nextConfig: NextConfig = {
  // Static export: `next build` writes plain files to `web/out`, which the
  // Python backend (`evalcascade serve`) serves at `/` next to the API at `/api`.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  // Don't let `next dev` generate coding-agent instruction files in the project.
  agentRules: false,
  turbopack: {
    // Without the mock flag, swap the demo fixtures for a stub so they are not
    // bundled into production output at all.
    resolveAlias: mockEnabled ? {} : { "@/lib/mock": "./src/lib/mock/disabled.ts" },
  },
};

export default nextConfig;
