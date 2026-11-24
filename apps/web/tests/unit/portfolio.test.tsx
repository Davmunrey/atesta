// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Portfolio } from "@/components/portfolio";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const m = (id: string, name: string, role: "owner" | "auditor" = "owner") => ({ organization_id: id, organization_name: name, role, access_expires_on: role === "auditor" ? "2027-01-01" : null, closure_erase_after: null });
const summary = (frameworks: number, assessed: number, total: number, overdue: number, pending = 0, pendingOverdue = 0, last: string | null = null) => ({
  frameworks_in_progress: frameworks, assessed, total, overdue, pending, pending_overdue: pendingOverdue, last_assessed_at: last,
});
const row = (id: string, name: string, role: "owner" | "auditor", s: ReturnType<typeof summary> | null) => ({ organization_id: id, organization_name: name, role, summary: s });
const names = (table: HTMLElement) => within(table).getAllByRole("link").map((a) => a.textContent);

it("shows the server's rows in the server's order, from one request, and summarises them", async () => {
  // Most urgent first is decided by the API (issue 228): the page keeps the order it is given.
  const calls = stubApi({
    "GET /api/v1/portfolio": [200, { not_shown: 0, rows: [
      row("urgent", "Urgente S.A.", "owner", summary(1, 10, 73, 3, 2, 1)),
      row("calm", "Calma S.L.", "owner", summary(1, 73, 73, 0, 0, 0, "2026-11-20T10:00:00Z")),
      row("fresh", "Nueva S.L.", "auditor", summary(0, 0, 0, 0)),
    ] }],
  });
  renderWithProviders(<Portfolio memberships={[m("calm", "Calma S.L."), m("urgent", "Urgente S.A."), m("fresh", "Nueva S.L.", "auditor")]} />);
  const table = await screen.findByRole("table");
  expect(names(table)).toEqual(["Calma S.L.", "Urgente S.A.", "Nueva S.L."]); // what the session knows, while loading
  expect(within(table).getAllByText("Cargando…")).toHaveLength(3);
  await vi.waitFor(() => { if (names(table)[0] !== "Urgente S.A.") throw new Error(String(names(table))); });
  const rows = within(table).getAllByRole("row").slice(1);
  expect(names(table)).toEqual(["Urgente S.A.", "Calma S.L.", "Nueva S.L."]);
  expect(within(rows[0]!).getByText("10 de 73")).toBeTruthy();
  expect(within(rows[0]!).getByText("3")).toBeTruthy();
  expect(within(rows[0]!).getByText("2 (1 vencida)")).toBeTruthy();
  expect(within(rows[0]!).getByText(/1 marco en curso/)).toBeTruthy();
  expect(within(rows[2]!).getByText("Sin empezar")).toBeTruthy();
  expect(within(rows[2]!).getByText(/Auditor/)).toBeTruthy();
  const list = screen.getByRole("list", { name: "Resumen de la cartera" });
  expect(within(list).getByText("3 organizaciones")).toBeTruthy();
  expect(within(list).getByText("1 con algo vencido")).toBeTruthy();
  expect(within(list).getByText("1 sin empezar")).toBeTruthy();
  expect(within(list).queryByText(/sin mostrar/)).toBeNull();
  expect(calls.map((c) => new URL(c.url).pathname)).toEqual(["/api/v1/portfolio"]); // one request, whatever the number of organizations
});

it("keeps the other rows when one organization could not be read, in English", async () => {
  stubApi({
    "GET /api/v1/portfolio": [200, { not_shown: 0, rows: [
      row("ok", "Fine Ltd", "owner", summary(1, 5, 10, 0)),
      row("broken", "Broken Ltd", "owner", null),
    ] }],
  });
  renderWithProviders(<Portfolio memberships={[m("ok", "Fine Ltd"), m("broken", "Broken Ltd")]} />, "en");
  expect(await screen.findByText("5 of 10")).toBeTruthy();
  expect(await screen.findByText("Could not load")).toBeTruthy();
});

it("says how many organizations the server left out, and counts them", async () => {
  stubApi({ "GET /api/v1/portfolio": [200, { not_shown: 2, rows: [row("a", "Alfa", "owner", summary(0, 0, 0, 0))] }] });
  renderWithProviders(<Portfolio memberships={[m("a", "Alfa"), m("b", "Beta"), m("c", "Gamma")]} />);
  expect(await screen.findByText("2 organizaciones más sin mostrar")).toBeTruthy();
  expect(screen.getByText("3 organizaciones")).toBeTruthy();
});

it("says every row could not be loaded when the request fails", async () => {
  stubApi({ "GET /api/v1/portfolio": [500, {}] });
  renderWithProviders(<Portfolio memberships={[m("a", "Alfa"), m("b", "Beta")]} />);
  expect(await screen.findAllByText("No se ha podido cargar")).toHaveLength(2);
  expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual(["Alfa", "Beta"]);
});
