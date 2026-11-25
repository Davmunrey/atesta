import { PHASE_DEVELOPMENT_SERVER, PHASE_PRODUCTION_BUILD } from "next/constants";
import { expect, it } from "vitest";
import config from "../../next.config";

it("production builds a static export without rewrites", async () => {
  const built = await config(PHASE_PRODUCTION_BUILD);
  expect(built.output).toBe("export");
  expect(built.rewrites).toBeUndefined();
});

it("the dev server rewrites /api and /auth to the local operator API, not the customer API", async () => {
  const rewrites = await (await config(PHASE_DEVELOPMENT_SERVER)).rewrites?.();
  expect(rewrites).toEqual([
    { source: "/api/:path*", destination: "http://localhost:8001/api/:path*" },
    { source: "/auth/:path*", destination: "http://localhost:8001/auth/:path*" },
  ]);
});

it("compiles the shared UI package and never writes Next's agent instructions (ADR-013, ADR-017)", async () => {
  for (const phase of [PHASE_PRODUCTION_BUILD, PHASE_DEVELOPMENT_SERVER]) {
    expect((await config(phase)).transpilePackages).toContain("@atesta/ui");
    expect((await config(phase)).agentRules).toBe(false);
  }
});
