// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { GettingStarted } from "@/components/getting-started";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.localStorage.clear(); });
const admin = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const base = "/api/v1/orgs/primary";
const ens = { key: "ens", name: "ENS", total: 73, assessed: 12, implemented: 0, partial: 0, not_implemented: 0, not_applicable: 0, has_axes: true,
  scope_defined: true, review_on: null, overdue: 0, unowned_open: 0, open_by_owner: {}, last_assessed_at: null };
const policy = { id: "p", title: "P", location_url: "https://x.test", review_months: 12, created_at: "2026-11-01T00:00:00Z",
  latest: { version: "1", approver_name: "C", approved_on: "2026-11-01", sha256: null, recorded_at: "2026-11-01T00:00:00Z" }, next_review_on: "2027-11-01" };

it("marks each step from the organization's own records and links to where it is done", async () => {
  stubApi({
    [`GET ${base}/members`]: [200, [{ user_id: "a" }]],
    [`GET ${base}/policies`]: [200, [policy]],
    [`GET ${base}/access-reviews`]: [200, []],
    [`GET ${base}/training-campaigns`]: [200, []],
    [`GET ${base}/api-tokens`]: [200, []],
  });
  renderWithProviders(<GettingStarted org={admin} readiness={[ens]} />);
  expect(await screen.findByText("3 de 7 pasos hechos. Cada paso se marca solo cuando lo registras.")).toBeTruthy();
  const scope = screen.getByRole("link", { name: "Define el alcance de ENS" });
  expect(scope.closest("li")?.getAttribute("data-done")).toBe("true");
  expect(screen.getByRole("link", { name: "Evalúa tus primeras medidas (10 de 10)" }).closest("li")?.getAttribute("data-done")).toBe("true");
  const team = screen.getByRole("link", { name: "Invita a tu equipo" });
  expect(team.closest("li")?.getAttribute("data-done")).toBe("false");
  expect(team.getAttribute("href")).toBe("/app/invitations?org=primary");
  expect(screen.getByRole("link", { name: "Registra la revisión y abre el dossier de ENS" }).getAttribute("href")).toBe("/app/dossier?org=primary&framework=ens");
});

it("can be hidden, and is never shown to auditors", async () => {
  stubApi({ [`GET ${base}/policies`]: [200, []], [`GET ${base}/access-reviews`]: [200, []], [`GET ${base}/training-campaigns`]: [200, []], [`GET ${base}/members`]: [200, []], [`GET ${base}/api-tokens`]: [200, []] });
  renderWithProviders(<GettingStarted org={admin} readiness={[ens]} />, "en");
  fireEvent.click(await screen.findByRole("button", { name: "Hide" }));
  expect(screen.queryByText("Getting started")).toBeNull();
  cleanup(); window.localStorage.clear();
  renderWithProviders(<GettingStarted org={{ ...admin, role: "auditor", access_expires_on: "2027-01-01" }} readiness={[ens]} />);
  expect(screen.queryByText("Puesta en marcha")).toBeNull();
});
