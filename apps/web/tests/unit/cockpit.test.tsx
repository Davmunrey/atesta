// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { OverviewDashboard } from "@/components/overview-dashboard";
import { nextStep } from "@/components/readiness";
import type { Readiness } from "@/lib/api/register-hooks";
import { overview } from "../fixtures/overview";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const r = (over: Partial<Readiness> = {}): Readiness => ({
  key: "synthetic_alpha", name: "Synthetic Alpha", total: 10, assessed: 0, implemented: 0, partial: 0, not_implemented: 0,
  not_applicable: 0, has_axes: true, scope_defined: false, review_on: null, overdue: 0, unowned_open: 0, open_by_owner: {},
  last_assessed_at: null, ...over,
});
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const routes = (readiness: Readiness[]) => ({
  "GET /api/v1/orgs/primary/overview": [200, overview] as [number, unknown],
  "GET /api/v1/orgs/primary/readiness": [200, readiness] as [number, unknown],
  "GET /api/v1/orgs/primary/my-work": [200, []] as [number, unknown],
  "GET /api/v1/orgs/primary/members": [200, []] as [number, unknown],
  "GET /api/v1/orgs/primary/activity": [200, { days: 30, daily: [], events: [] }] as [number, unknown],
});

it("walks the self-assessment one step at a time", () => {
  expect(nextStep(r())).toEqual({ kind: "scope", count: 0 });
  expect(nextStep(r({ scope_defined: true, assessed: 4 }))).toEqual({ kind: "assess", count: 6 });
  expect(nextStep(r({ has_axes: false, assessed: 10 }))).toEqual({ kind: "review", count: 0 });
  expect(nextStep(r({ has_axes: false, assessed: 10, review_on: "2026-11-20" }))).toEqual({ kind: "export", count: 0 });
});

it("summarizes progress in one sentence and lists only what truly needs attention", async () => {
  stubApi(routes([r({ scope_defined: true, assessed: 6, implemented: 4, partial: 1, not_implemented: 1, overdue: 2, unowned_open: 3 })]));
  renderWithProviders(<OverviewDashboard orgId="primary" org={owner} />);
  expect(await screen.findByText(/Synthetic Alpha: 6 de 10 medidas evaluadas, 4 implantadas\./)).toBeTruthy();
  expect(screen.getByText("Hay 2 asuntos que requieren atención.")).toBeTruthy();
  const now = within(screen.getByRole("region", { name: "Ahora" }));
  const items = now.getAllByRole("listitem").map((li) => li.textContent);
  expect(items).toEqual([
    "Vencido2 medidas con fecha límite vencida en Synthetic Alpha",
    "Pendiente3 medidas abiertas sin responsable en Synthetic Alpha",
  ]);
  expect(now.getByRole("link", { name: /vencida/ }).getAttribute("href")).toBe("/app/framework?org=primary&framework=synthetic_alpha");
});

it("asks for the security officer's review only once the self-assessment is complete", async () => {
  stubApi(routes([r({ has_axes: false, assessed: 10, implemented: 10 })]));
  renderWithProviders(<OverviewDashboard orgId="primary" org={owner} />);
  const now = within(await screen.findByRole("region", { name: "Ahora" }));
  expect(now.getByText(/Revisión del responsable de la seguridad de Synthetic Alpha/)).toBeTruthy();
});

it("names the next step when nothing is urgent", async () => {
  stubApi(routes([r({ scope_defined: true, assessed: 3, implemented: 3 })]));
  renderWithProviders(<OverviewDashboard orgId="primary" org={owner} />);
  const now = within(await screen.findByRole("region", { name: "Ahora" }));
  expect(now.getByText(/Nada urgente\. Siguiente paso:/)).toBeTruthy();
  expect(now.getByRole("link", { name: "Evalúa 7 medidas pendientes de Synthetic Alpha" })).toBeTruthy();
});

it("writes the bar's numbers as text and never calls a self-assessed framework unassessed", async () => {
  stubApi(routes([r({ scope_defined: true, assessed: 6, implemented: 4, partial: 1, not_implemented: 0, not_applicable: 1 })]));
  renderWithProviders(<OverviewDashboard orgId="primary" org={owner} />);
  expect(await screen.findByText("6 de 10 evaluadas · 4 implantadas · 1 en parte · 0 sin implantar · 1 no aplica")).toBeTruthy();
  expect(document.querySelector(".readiness-bar")?.getAttribute("aria-hidden")).toBe("true");
});

it("keeps first steps for an organization that has not started", async () => {
  stubApi({ ...routes([r()]), "GET /api/v1/orgs/primary/frameworks/synthetic_alpha/register": [404, {}] });
  renderWithProviders(<OverviewDashboard orgId="primary" org={owner} />);
  await screen.findByText("Synthetic Alpha");
  expect(screen.queryByRole("region", { name: "Ahora" })).toBeNull();
});
