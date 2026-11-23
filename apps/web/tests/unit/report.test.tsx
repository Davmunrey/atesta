// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ReportView } from "@/components/report-view";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const zero = { measures_assessed: 0, assessments_reviewed: 0, evidence_by_people: 0, evidence_by_tools: 0, policies_approved: 0, access_reviews_closed: 0,
  trainings_closed: 0, incidents_recorded: 0, incidents_closed: 0, deadlines_met: 0, people_joined: 0 };
const report = (done: Partial<typeof zero>) => ({
  month: "2026-11", starts: "2026-10-31T23:00:00Z", ends: "2026-11-30T23:00:00Z", generated_at: "2026-11-23T12:00:00Z",
  statement: "Not a certification", status_is_current: true, done: { ...zero, ...done },
  frameworks: [{ key: "ens", name: "ENS", total: 73, assessed: 40, implemented: 24, partial: 6, not_implemented: 6, not_applicable: 4,
    has_axes: true, scope_defined: true, review_on: "2026-11-20", overdue: 2, unowned_open: 0, open_by_owner: {}, last_assessed_at: null }],
  due: [{ kind: "policy_unapproved", id: "p", title: "Política de uso aceptable", due_on: null, overdue: false, due_at: null, clock: null }],
});

it("shows what was done in the month, the current status and what falls due", async () => {
  stubApi({ "GET /api/v1/orgs/primary/report": [200, report({ measures_assessed: 40, policies_approved: 2 })] });
  renderWithProviders(<ReportView org={owner} initialMonth="2026-11" />);
  const done = await screen.findByRole("region", { name: "Hecho en noviembre de 2026" });
  expect(within(done).getByText("Medidas evaluadas")).toBeTruthy();
  expect(within(done).getByText("40")).toBeTruthy();
  expect(within(done).queryByText("Incidentes cerrados")).toBeNull(); // zero lines are left out
  expect(screen.getByText("Es el estado actual, no el del final del mes.")).toBeTruthy();
  expect(screen.getByText("40 de 73")).toBeTruthy();
  expect(screen.getByText("Registrar la aprobación de la política «Política de uso aceptable»")).toBeTruthy();
});

it("says so when nothing happened, in English", async () => {
  stubApi({ "GET /api/v1/orgs/primary/report": [200, { ...report({}), frameworks: [], due: [] }] });
  renderWithProviders(<ReportView org={owner} initialMonth="2026-11" />, "en");
  expect(await screen.findByText("No activity was recorded this month.")).toBeTruthy();
  expect(screen.getByText("Nothing falls due.")).toBeTruthy();
});
