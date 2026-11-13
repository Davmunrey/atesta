import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const API = process.env.ATESTA_API_URL ?? "http://localhost:8000";

/**
 * Production is a static export; CloudFront routes /api and /auth to the API (infra spec).
 * The dev server keeps the same single origin by rewriting those paths to the local API.
 */
export default async function config(phase: string): Promise<NextConfig> {
  const shared: NextConfig = {
    reactStrictMode: true,
    images: { unoptimized: true },
    // `next dev` would write its own agent instructions into AGENTS.md; ADR-013 vendors those.
    agentRules: false,
    devIndicators: false,
  };
  if (phase !== PHASE_DEVELOPMENT_SERVER) return { ...shared, output: "export" };
  return {
    ...shared,
    rewrites: async () => [
      { source: "/api/:path*", destination: `${API}/api/:path*` },
      { source: "/auth/:path*", destination: `${API}/auth/:path*` },
    ],
  };
}
