// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Portfolio } from "@/components/portfolio";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const m = (id: string, name: string, role: "owner" | "auditor" = "owner") => ({ organization_id: id, organization_name: name, role, access_expires_on: role === "auditor" ? "2027-01-01" : null, closure_erase_after: null });
const fw = (assessed: number, total: number, overdue: number, last: string | null = null) => ({
  key: "ens", name: "ENS", total, assessed, implemented: 0, partial: 0, not_implemented: 0, not_applicable: 0, has_axes: false,
  scope_defined: false, review_on: null, overdue, unowned_open: 0, open_by_owner: {}, last_assessed_at: last,
});
const due = (overdue: boolean) => ({ kind: "policy_review", id: "p", title: "Política", due_on: "2026-11-01", overdue, due_at: null, clock: null });

it("orders organizations by urgency and summarises the portfolio", async () => {
  stubApi({
    "GET /api/v1/orgs/calm/readiness": [200, [fw(73, 73, 0, "2026-11-20T10:00:00Z")]],
    "GET /api/v1/orgs/calm/routines/due": [200, []],
    "GET /api/v1/orgs/urgent/readiness": [200, [fw(10, 73, 3), { ...fw(0, 162, 0), key: "untouched" }]],
    "GET /api/v1/orgs/urgent/routines/due": [200, [due(true), due(false)]],
    "GET /api/v1/orgs/fresh/readiness": [200, [fw(0, 73, 0)]],
    "GET /api/v1/orgs/fresh/routines/due": [200, []],
  });
  renderWithProviders(<Portfolio memberships={[m("calm", "Calma S.L."), m("urgent", "Urgente S.A."), m("fresh", "Nueva S.L.", "auditor")]} />);
  const table = await screen.findByRole("table");
  await vi.waitFor(() => {
    const names = within(table).getAllByRole("link").map((a) => a.textContent);
    if (names[0] !== "Urgente S.A.") throw new Error(String(names));
  });
  const rows = within(table).getAllByRole("row").slice(1);
  expect(rows.map((r) => within(r).getByRole("link").textContent)).toEqual(["Urgente S.A.", "Calma S.L.", "Nueva S.L."]);
  expect(within(rows[0]!).getByText("10 de 73")).toBeTruthy();
  expect(within(rows[0]!).getByText("3")).toBeTruthy();
  expect(within(rows[0]!).getByText("2 (1 vencida)")).toBeTruthy();
  const summary = screen.getByRole("list", { name: "Resumen de la cartera" });
  expect(within(summary).getByText("3 organizaciones")).toBeTruthy();
  expect(within(summary).getByText("1 con algo vencido")).toBeTruthy();
  expect(within(summary).getByText("1 sin empezar")).toBeTruthy();
  expect(within(rows[2]!).getByText("Sin empezar")).toBeTruthy();
});

it("keeps the other rows when one organization fails, in English", async () => {
  stubApi({
    "GET /api/v1/orgs/ok/readiness": [200, [fw(5, 10, 0)]],
    "GET /api/v1/orgs/ok/routines/due": [200, []],
    "GET /api/v1/orgs/broken/readiness": [500, {}],
    "GET /api/v1/orgs/broken/routines/due": [500, {}],
  });
  renderWithProviders(<Portfolio memberships={[m("ok", "Fine Ltd"), m("broken", "Broken Ltd")]} />, "en");
  expect(await screen.findByText("5 of 10")).toBeTruthy();
  expect(await screen.findByText("Could not load")).toBeTruthy();
});
