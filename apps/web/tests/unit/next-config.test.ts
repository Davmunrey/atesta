import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } from "next/constants";
import { expect, it } from "vitest";
import config from "../../next.config";

it("production builds a static export without rewrites", async () => {
  const built = await config(PHASE_PRODUCTION_BUILD);
  expect(built.output).toBe("export");
  expect(built.rewrites).toBeUndefined();
});

it("the dev server rewrites /api and /auth to the local API", async () => {
  const dev = await config(PHASE_DEVELOPMENT_SERVER);
  expect(dev.output).toBeUndefined();
  const rewrites = await dev.rewrites?.();
  expect(rewrites).toEqual([
    { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
    { source: "/auth/:path*", destination: "http://localhost:8000/auth/:path*" },
  ]);
});

it("never writes Next's agent instructions into the repo (ADR-013)", async () => {
  for (const phase of [PHASE_PRODUCTION_BUILD, PHASE_DEVELOPMENT_SERVER]) {
    expect((await config(phase)).agentRules).toBe(false);
  }
});

it("compiles the shared UI package with the app, in every phase (ADR-017)", async () => {
  for (const phase of [PHASE_PRODUCTION_BUILD, PHASE_DEVELOPMENT_SERVER]) {
    expect((await config(phase)).transpilePackages).toContain("@atesta/ui");
  }
});
