// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ActivityView } from "@/components/activity-view";
import { ColumnChart, LineChart, RankedBars, ticks } from "@/components/charts";
import { OwnerInsights, ProgressInsights } from "@/components/insights";
import { isOverdue, workload, type Register } from "@/lib/api/register-hooks";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const base = "/api/v1/orgs/primary/frameworks/synthetic_alpha";
const item = (code: string, over: Partial<Register["items"][number]> = {}): Register["items"][number] => ({
  code, title_es: code, title_en: null, selection_basis: null, proposal: { decision: "undecided", rule: null, level: null }, assessment: null, assignment: null, ...over,
});
const assessed = (implementation: "implemented" | "not_implemented", applicability: "applies" | "not_applicable" = "applies") => ({
  applicability, implementation, regularly_reviewed: false, justification: "", performed_by: "", performed_on: null, evidence_statement_ids: [], notes: "", recorded_by: "u", recorded_at: "2026-11-20T10:00:00Z",
});
const register: Register = {
  framework_key: "synthetic_alpha", framework_version: "2", catalog_version: "c", axes: {}, groups_es: [], scope: null, review: null,
  items: [
    item("a.1", { assessment: assessed("implemented"), assignment: { owner_user_id: "u-ana", due_on: "2026-12-31", assigned_at: "2026-11-20T10:00:00Z" } }),
    item("a.2", { assignment: { owner_user_id: "u-ana", due_on: "2026-01-01", assigned_at: "2026-11-20T10:00:00Z" } }),
    item("a.3", { assignment: { owner_user_id: "u-luis", due_on: null, assigned_at: "2026-11-20T10:00:00Z" } }),
    item("a.4", { assessment: assessed("not_implemented", "not_applicable") }),
    item("a.5"),
  ],
};

it("rounds axis ticks to clean steps", () => {
  expect(ticks(7)).toEqual([0, 2, 4, 6, 8]);
  expect(ticks(73)).toEqual([0, 20, 40, 60, 80]);
  expect(ticks(0)).toEqual([0, 1]);
  expect(ticks(1, true)).toEqual([0, 1]); // counts: never 0 / 0.5 / 1
  expect(ticks(2, true)).toEqual([0, 1, 2]);
});

it("draws a line with its end value, a table view and a keyboard-driven readout", () => {
  renderWithProviders(<LineChart title="Implantadas" valueLabel="Implantadas" tableLabel="Ver tabla"
    points={[{ label: "1 nov", value: 1 }, { label: "2 nov", value: 3 }, { label: "3 nov", value: 4 }]} />);
  const chart = screen.getByRole("img", { name: /Implantadas/ });
  expect(chart.querySelector(".chart-end-label")?.textContent).toBe("4");
  expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(4);
  fireEvent.keyDown(chart, { key: "Home" });
  expect(screen.getByRole("status").textContent).toContain("1 nov");
  fireEvent.keyDown(chart, { key: "ArrowRight" });
  expect(screen.getByRole("status").textContent).toContain("2 nov");
});

it("draws columns only for non-zero days and lists every day in the table", () => {
  renderWithProviders(<ColumnChart title="Acciones" valueLabel="Acciones" tableLabel="Ver tabla"
    points={[{ label: "1", value: 0 }, { label: "2", value: 5 }, { label: "3", value: 2 }]} />);
  expect(document.querySelectorAll(".chart-bar")).toHaveLength(2);
  expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(4);
});

it("ranks bars largest first, with the value at the tip", () => {
  renderWithProviders(<RankedBars title="Abiertas" empty="—" rows={[{ label: "luis", value: 1 }, { label: "ana", value: 3 }]} />);
  const labels = Array.from(document.querySelectorAll(".ranked-label")).map((n) => n.textContent);
  expect(labels).toEqual(["ana", "luis"]);
  expect(document.querySelector(".ranked-value")?.textContent).toBe("3");
});

it("counts open measures per owner and flags only unfinished ones past their date", () => {
  expect(Object.fromEntries(workload(register.items))).toEqual({ "u-ana": 1, "u-luis": 1, null: 1 });
  expect(register.items.map((i) => isOverdue(i, "2026-11-22"))).toEqual([false, true, false, false, false]);
});

it("hides the progress chart until two days of history exist", async () => {
  stubApi({ [`GET ${base}/register/history`]: [200, [{ day: "2026-11-20", assessed: 1, implemented: 1, not_applicable: 0 }]], [`GET ${base}/trend`]: [200, []] });
  renderWithProviders(<ProgressInsights orgId="primary" frameworkKey="synthetic_alpha" register={register} />);
  expect(await screen.findByText(/al menos dos días distintos/)).toBeTruthy();
  expect(screen.getByText("2 / 5")).toBeTruthy();
});

it("plots implemented measures once history spans two days", async () => {
  stubApi({ [`GET ${base}/register/history`]: [200, [
    { day: "2026-11-20", assessed: 1, implemented: 0, not_applicable: 0 },
    { day: "2026-11-21", assessed: 2, implemented: 1, not_applicable: 1 },
  ]], [`GET ${base}/trend`]: [200, []] });
  renderWithProviders(<ProgressInsights orgId="primary" frameworkKey="synthetic_alpha" register={register} />);
  expect(await screen.findByRole("img", { name: /Medidas implantadas a lo largo del tiempo/ })).toBeTruthy();
  expect(screen.queryByRole("img", { name: /Puntuación registrada/ })).toBeNull();
});

it("shows owners by email with their open measures, the unowned and the overdue", async () => {
  stubApi({ "GET /api/v1/orgs/primary/members": [200, [
    { user_id: "u-ana", email: "ana@example.test", display_name: null, role: "admin" },
    { user_id: "u-luis", email: "luis@example.test", display_name: null, role: "member" },
  ]] });
  renderWithProviders(<OwnerInsights orgId="primary" register={register} />);
  expect(await screen.findByText("ana@example.test")).toBeTruthy();
  const tiles = document.querySelectorAll(".stat-tiles dd");
  expect(Array.from(tiles).map((d) => d.textContent)).toEqual(["1", "1"]);
});

it("names an owner who has left the organization", async () => {
  stubApi({ "GET /api/v1/orgs/primary/members": [200, []] });
  renderWithProviders(<OwnerInsights orgId="primary" register={register} />);
  expect((await screen.findAllByText("Antiguo miembro")).length).toBeGreaterThan(0);
});

it("lists activity with readable action names, and keeps members out", async () => {
  stubApi({ "GET /api/v1/orgs/primary/activity": [200, { days: 30, daily: [{ day: "2026-11-21", count: 0 }, { day: "2026-11-22", count: 2 }],
    events: [{ occurred_at: "2026-11-22T10:00:00Z", actor_email: "ana@example.test", action: "requirement.assessed", target_type: "requirement", target_id: "ens:org.1" }] }] });
  const membership = { organization_id: "primary", organization_name: "Org", role: "admin" as const };
  renderWithProviders(<ActivityView org={membership} />);
  expect(await screen.findByText("Evaluó una medida")).toBeTruthy();
  expect(screen.getByText("ana@example.test")).toBeTruthy();
  cleanup();
  renderWithProviders(<ActivityView org={{ ...membership, role: "member" }} />);
  expect(screen.getByText("Solo las personas administradoras pueden ver la actividad.")).toBeTruthy();
});
