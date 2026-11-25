import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const API = process.env.ATESTA_OPERATOR_API_URL ?? "http://localhost:8001";

/**
 * The operator portal (ADR-017): a static export on its own hostname; the admin distribution
 * routes /api and /auth to the operator API. The dev server keeps that single origin by rewriting
 * those paths to the local operator API, as the console's does.
 */
export default async function config(phase: string): Promise<NextConfig> {
  const shared: NextConfig = {
    reactStrictMode: true,
    images: { unoptimized: true },
    // `next dev` would write its own agent instructions into AGENTS.md; ADR-013 vendors those.
    agentRules: false,
    devIndicators: false,
    // The shared UI set ships as TypeScript source (ADR-017); Next compiles it with the app.
    transpilePackages: ["@atesta/ui"],
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
