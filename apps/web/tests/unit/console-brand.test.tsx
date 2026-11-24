// @vitest-environment jsdom
import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AppLayout from "@/app/(app)/app/layout";
import { FrameworkLines } from "@/components/framework-lines";
import { overview } from "../fixtures/overview";
import { renderWithProviders, stubApi } from "./render";

// The brand in the console (ui-polish spec, issue 330).
vi.mock("next/navigation", () => ({
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ push: vi.fn() }),
}));
const me = { id: "u", email: "brand@example.test", email_verified: true, locale: "es",
  memberships: [{ organization_id: "primary", organization_name: "Synthetic Team", role: "owner", access_expires_on: null, closure_erase_after: null }] };
beforeEach(() => window.history.replaceState(null, "", "/app/org?org=primary"));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("shows the seal lockup in the top bar, named by the brand", async () => {
  stubApi({ "GET /api/v1/me": [200, me], "GET /api/v1/orgs/primary/overview": [200, overview] });
  renderWithProviders(<AppLayout><h1>Page</h1></AppLayout>);
  const home = await screen.findByRole("link", { name: "Atesta" });
  expect(home.querySelector("svg.brand-seal[aria-hidden='true']")).toBeTruthy();
});

it("marks the lead framework's measures assessed as the home's one key figure", () => {
  const row = { key: "ens", name: "ENS", total: 73, assessed: 40, implemented: 24, partial: 0, not_implemented: 0, not_applicable: 0, has_axes: true,
    scope_defined: true, review_on: null, overdue: 0, unowned_open: 0, open_by_owner: {}, last_assessed_at: "2026-11-01T00:00:00Z" };
  const framework = { key: "ens", name: "ENS", version: "1", status: "released" as const, requirements: 73, snapshot: null };
  renderWithProviders(<FrameworkLines frameworks={[framework, { ...framework, key: "nis2", name: "NIS2" }]} readiness={[row, { ...row, key: "nis2", assessed: 3 }]} orgId="primary" />);
  const key = document.querySelectorAll(".key-figure");
  expect(key).toHaveLength(1);
  expect(key[0]!.textContent).toBe("40");
});
