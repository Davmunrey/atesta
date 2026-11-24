// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GettingStarted } from "@/components/getting-started";
import { IncidentView } from "@/components/incident-view";
import { OverviewDashboard } from "@/components/overview-dashboard";
import { RecordsGlance } from "@/components/records-glance";
import type { Readiness } from "@/lib/api/register-hooks";
import { countdown } from "@/lib/deadline";
import { overview } from "../fixtures/overview";
import { renderWithProviders, stubApi } from "./render";

// Home and urgency (console-unification spec, part 1).
const NOW = new Date("2026-11-24T09:00:00Z");
beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); vi.setSystemTime(NOW); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); window.localStorage.clear(); });

const base = "/api/v1/orgs/primary";
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const alpha = (over: Partial<Readiness> = {}): Readiness => ({
  key: "synthetic_alpha", name: "Synthetic Alpha", total: 10, assessed: 6, implemented: 4, partial: 1, not_implemented: 1,
  not_applicable: 0, has_axes: true, scope_defined: true, review_on: null, overdue: 2, unowned_open: 3, open_by_owner: {},
  last_assessed_at: null, ...over,
});
const measure = (code: string, due: string | null) => ({
  framework_key: "synthetic_alpha", framework_name: "Synthetic Alpha", code, title_es: `Medida ${code}`, title_en: null,
  due_on: due, applicability: null, implementation: null,
});
const clockDue = { kind: "incident_clock", id: "i1", title: "Phishing", due_on: "2026-11-25", due_at: "2026-11-25T17:00:00Z", overdue: false,
  clock: { es: "Notificación a la autoridad de control", en: "Notification to the supervisory authority", framework: "RGPD" } };

it("counts a deadline down in hours, then days, rounding time left up and time past down", () => {
  expect(countdown("2026-11-25T17:00:00Z", NOW)).toEqual({ past: false, unit: "hours", value: 32 });
  expect(countdown("2026-11-24T09:00:01Z", NOW)).toEqual({ past: false, unit: "hours", value: 1 });
  expect(countdown("2026-11-27T10:00:00Z", NOW)).toEqual({ past: false, unit: "days", value: 4 });
  expect(countdown("2026-11-24T03:30:00Z", NOW)).toEqual({ past: true, unit: "hours", value: 5 });
  expect(countdown("2026-11-24T08:30:00Z", NOW)).toEqual({ past: true, unit: "hours", value: 1 });
  expect(countdown("2026-11-20T09:00:00Z", NOW)).toEqual({ past: true, unit: "days", value: 4 });
});

it("puts one ordered task list first: legal clocks, overdue, my week, then the rest", async () => {
  stubApi({
    [`GET ${base}/overview`]: [200, overview],
    [`GET ${base}/readiness`]: [200, [alpha()]],
    [`GET ${base}/members`]: [200, []],
    [`GET ${base}/my-work`]: [200, [measure("op.1", "2026-11-20"), measure("op.2", "2026-11-27"), measure("op.3", "2026-12-20")]],
    [`GET ${base}/routines/due`]: [200, [
      { kind: "policy_unapproved", id: "p1", title: "Uso aceptable", due_on: null, overdue: false, due_at: null, clock: null },
      { kind: "access_review_overdue", id: "a1", title: "Cuentas M365", due_on: "2026-11-10", overdue: true, due_at: null, clock: null },
      clockDue,
    ]],
  });
  renderWithProviders(<OverviewDashboard orgId="primary" org={owner} />);
  const now = within(await screen.findByRole("region", { name: "Ahora" }));
  await vi.waitFor(() => { if (now.getAllByRole("listitem").length < 7) throw new Error("loading"); });
  expect(now.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "Quedan 32 hNotificación a la autoridad de control (RGPD) del incidente «Phishing»: vence el 25 nov 2026, 17:00",
    "VencidoTerminar la revisión de accesos «Cuentas M365» (vencía el 10 de noviembre de 2026)",
    "Vencidoop.1 Medida op.1 · venció el 20 nov 2026",
    "Vencido1 medida más con fecha límite vencida en Synthetic Alpha",
    "27 nov 2026op.2 Medida op.2",
    "Pendiente3 medidas abiertas sin responsable en Synthetic Alpha",
    "FaltaRegistrar la aprobación de la política «Uso aceptable»",
  ]);
  // My later measures live in Mi trabajo, linked from the panel.
  expect(now.queryByText(/op\.3/)).toBeNull();
  expect(now.getByRole("link", { name: "Ver todo en Mi trabajo" }).getAttribute("href")).toBe("/app/my-work?org=primary");
  // The running clock has its own severity, never a grey "Pendiente".
  expect(now.getByText("Quedan 32 h").closest(".badge")?.getAttribute("data-severity")).toBe("clock");
});

it("leaves the KPI strip, team, activity and scans off the home, and shows each figure once", async () => {
  stubApi({
    [`GET ${base}/overview`]: [200, overview],
    [`GET ${base}/readiness`]: [200, [alpha({ key: "synthetic_alpha", overdue: 0, unowned_open: 0 })]],
    [`GET ${base}/members`]: [200, []], [`GET ${base}/my-work`]: [200, []], [`GET ${base}/routines/due`]: [200, []],
  });
  renderWithProviders(<OverviewDashboard orgId="primary" org={owner} />);
  const frameworks = within(await screen.findByRole("region", { name: "Marcos" }));
  const regions = screen.getAllByRole("region").map((r) => r.getAttribute("aria-labelledby") && document.getElementById(r.getAttribute("aria-labelledby")!)?.textContent);
  expect(regions[0]).toBe("Ahora");
  for (const gone of ["Equipo", "Actividad reciente", "Últimos análisis", "Medidas evaluadas", "Marcos en curso"]) expect(screen.queryByText(gone)).toBeNull();
  expect(document.querySelector(".kpis")).toBeNull();
  expect(frameworks.getByRole("link", { name: "Synthetic Alpha" }).getAttribute("href")).toBe("/app/framework?org=primary&framework=synthetic_alpha");
  expect(frameworks.getByRole("link", { name: "Synthetic Alpha" }).closest("li")?.textContent).toBe("Synthetic Alpha6 de 10 medidas evaluadas · 4 implantadas");
  expect(frameworks.getByText("Último análisis: 0 %")).toBeTruthy();
  // The lead framework's measures assessed is the one key figure; templates stay on the Marcos page.
  const key = document.querySelectorAll(".key-figure");
  expect(key).toHaveLength(1);
  expect(key[0]!.textContent).toBe("6");
  expect(frameworks.queryByText("Synthetic Delta")).toBeNull();
  expect(screen.getAllByText(/6 de 10/)).toHaveLength(1);
});

const tokens = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `t${i}` }));
const steps = (policies: unknown[], members: number, reviews: number, toks: number) => stubApi({
  [`GET ${base}/members`]: [200, Array.from({ length: members }, (_, i) => ({ user_id: `u${i}` }))],
  [`GET ${base}/policies`]: [200, policies], [`GET ${base}/access-reviews`]: [200, tokens(reviews)],
  [`GET ${base}/training-campaigns`]: [200, []], [`GET ${base}/api-tokens`]: [200, tokens(toks)],
});
const policy = { id: "p", title: "P", location_url: "https://x.test", review_months: 12, created_at: "2026-11-01T00:00:00Z",
  latest: { version: "1", approver_name: "C", approved_on: "2026-11-01", sha256: null, recorded_at: "2026-11-01T00:00:00Z" }, next_review_on: "2027-11-01" };
const ens = alpha({ key: "ens", name: "ENS", total: 73, assessed: 12, review_on: "2026-11-20" });

it("folds getting started to one line from five of seven steps, and hides it at seven", async () => {
  steps([policy], 1, 1, 1);
  renderWithProviders(<GettingStarted org={owner} readiness={[ens]} />);
  await vi.waitFor(() => { if (!document.querySelector(".getting-started-line")) throw new Error("loading"); });
  const next = screen.getByRole("link", { name: "Invita a tu equipo" });
  expect(next.closest("p")?.textContent).toBe("Puesta en marcha: 6 de 7 · Invita a tu equipo\u00a0→");
  expect(next.getAttribute("href")).toBe("/app/invitations?org=primary");
  expect(screen.queryByRole("list")).toBeNull();
  cleanup();
  steps([policy], 2, 1, 1);
  const { container } = renderWithProviders(<GettingStarted org={owner} readiness={[ens]} />);
  await vi.waitFor(() => { if (container.textContent) throw new Error("still shown"); });
  await new Promise((r) => setTimeout(r, 20));
  expect(container.textContent).toBe("");
});

it("never calls incidents up to date while a notification clock runs", async () => {
  stubApi({
    [`GET ${base}/policies`]: [200, []], [`GET ${base}/access-reviews`]: [200, []], [`GET ${base}/training-campaigns`]: [200, []],
    [`GET ${base}/incidents`]: [200, [{ id: "i1", title: "Phishing", aware_at: "2026-11-23T17:00:00Z", classified_at: null, significant: false,
      personal_data: true, created_at: "2026-11-23T17:00:00Z", closed_at: null, next_due_at: "2026-11-25T17:00:00Z", overdue: 0 }]],
  });
  renderWithProviders(<RecordsGlance org={owner} />);
  const row = (await screen.findByRole("link", { name: "Incidentes" })).closest("tr")!;
  await vi.waitFor(() => { if (!row.textContent?.includes("plazo")) throw new Error("loading"); });
  expect(row.textContent).not.toContain("Al día");
  expect(within(row).getByText("Quedan 32 h").closest(".badge")?.getAttribute("data-severity")).toBe("clock");
  expect(row.textContent).toContain("1 incidente abierto, 1 con un aviso por enviar en plazo.");
});

const incident = {
  id: "i1", title: "Phishing", aware_at: "2026-11-23T17:00:00Z", classified_at: null, significant: false, personal_data: true,
  created_at: "2026-11-23T17:00:00Z", closed_at: null, next_due_at: "2026-11-25T17:00:00Z", overdue: 0, updates: [],
  clocks: [{ ref: "gdpr:art33", framework_key: "gdpr", framework_name: "RGPD", requirement: "art33", title_es: "Notificación a la autoridad de control",
    title_en: "Notification to the supervisory authority", state: "running", due_at: "2026-11-25T17:00:00Z", met_at: null, late: false }],
};

it("makes sending the notice the primary action and asks before closing with a notice unsent", async () => {
  const requests = stubApi({ [`GET ${base}/incidents/i1`]: [200, incident], [`POST ${base}/incidents/i1/updates`]: [201, incident] });
  renderWithProviders(<IncidentView org={owner} incidentId="i1" />);
  const send = await screen.findByRole("button", { name: /^Marcar como enviado/ });
  expect(send.className).toContain("button-primary");
  expect(screen.getByText("Quedan 32 h")).toBeTruthy();
  const close = screen.getByRole("button", { name: "Cerrar el incidente" });
  expect(close.className).toContain("dashboard-button");
  fireEvent.click(close);
  expect(screen.getByText("Queda 1 aviso sin enviar. ¿Cerrar igualmente?")).toBeTruthy();
  expect(requests.filter((r) => r.method === "POST")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
  expect(screen.queryByText(/¿Cerrar igualmente\?/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Cerrar el incidente" }));
  fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
  await vi.waitFor(() => expect(requests.filter((r) => r.method === "POST")).toHaveLength(1));
  expect(await requests.find((r) => r.method === "POST")!.clone().json()).toEqual({ kind: "closed", note: "" });
});

it("closes at once when every notice has been sent", async () => {
  const met = { ...incident, next_due_at: null, clocks: [{ ...incident.clocks[0]!, state: "met", met_at: "2026-11-24T08:00:00Z" }] };
  const requests = stubApi({ [`GET ${base}/incidents/i1`]: [200, met], [`POST ${base}/incidents/i1/updates`]: [201, met] });
  renderWithProviders(<IncidentView org={owner} incidentId="i1" />);
  fireEvent.click(await screen.findByRole("button", { name: "Cerrar el incidente" }));
  await vi.waitFor(() => expect(requests.filter((r) => r.method === "POST")).toHaveLength(1));
});
