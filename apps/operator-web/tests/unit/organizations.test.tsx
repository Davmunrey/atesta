// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { OrganizationDetailPage } from "@/components/organization-detail";
import { OrganizationList } from "@/components/organization-list";
import { renderWithProviders, stubApi } from "./render";

let search = "";
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), useSearchParams: () => new URLSearchParams(search) }));

beforeEach(() => { search = ""; replace.mockReset(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const row = (n: number, extra: object = {}) => ({ id: `o-${n}`, name: `Organización ${n}`, state: "active", plan: "business", plan_default: true,
  members: 3, health: "ok", last_activity: "2026-11-20T10:00:00Z", created_at: "2026-11-01T10:00:00Z", ...extra });
const page = (rows: object[], total = rows.length, n = 1) => ({ rows, total, page: n, page_size: 50 });

it("lists organizations with their state, plan, members, connections and last activity", async () => {
  const requests = stubApi({ "GET /api/v1/organizations": [200, page([row(1), row(2, { state: "suspended", plan: "pro", plan_default: false, health: "attention", last_activity: null })])] });
  renderWithProviders(<OrganizationList />);
  const table = within(await screen.findByRole("region", { name: "Organizaciones encontradas" }));
  expect(table.getByRole("link", { name: "Organización 1" }).getAttribute("href")).toBe("/organization?id=o-1");
  expect(table.getByText("Business (por defecto)")).toBeTruthy();
  const suspended = table.getByRole("row", { name: /Organización 2/ });
  for (const text of ["Suspendida", "Pro", "Requieren atención", "Sin actividad"]) expect(within(suspended).getByText(text)).toBeTruthy();
  expect(suspended.querySelector('.badge[data-severity="overdue"]')?.textContent).toBe("Suspendida");
  expect(new URL(requests[0]!.url).search).toBe("?sort=name&page=1");
});

it("reads the search, filters, sort and page from the address and sends them to the API", async () => {
  search = "q=norte&state=suspended&plan=default&health=attention&billing=missing&sort=activity&page=2&bogus=1";
  const requests = stubApi({ "GET /api/v1/organizations": [200, page([row(51)], 51, 2)] });
  renderWithProviders(<OrganizationList />);
  await screen.findByRole("link", { name: "Organización 51" });
  expect(Object.fromEntries(new URL(requests[0]!.url).searchParams)).toEqual(
    { q: "norte", state: "suspended", plan: "default", health: "attention", billing: "missing", sort: "activity", page: "2" });
  expect((screen.getByLabelText("Estado") as HTMLSelectElement).value).toBe("suspended");
  expect(screen.getByRole("button", { name: "Conexiones que requieren atención" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByRole("status").textContent).toBe("51–51 de 51");
});

it("changing a filter, searching or turning the page updates the address", async () => {
  stubApi({ "GET /api/v1/organizations": [200, page(Array.from({ length: 50 }, (_, i) => row(i + 1)), 53)] });
  renderWithProviders(<OrganizationList />);
  await screen.findByRole("link", { name: "Organización 1" });
  fireEvent.change(screen.getByLabelText("Estado"), { target: { value: "closing" } });
  expect(replace).toHaveBeenLastCalledWith("/?state=closing");
  fireEvent.click(screen.getByRole("button", { name: "Sin datos de facturación" }));
  expect(replace).toHaveBeenLastCalledWith("/?billing=missing");
  fireEvent.change(screen.getByLabelText("Nombre o identificador"), { target: { value: " Norte " } });
  fireEvent.click(screen.getByRole("button", { name: "Buscar" }));
  expect(replace).toHaveBeenLastCalledWith("/?q=Norte");
  expect(screen.getByRole("status").textContent).toBe("1–50 de 53");
  fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
  expect(replace).toHaveBeenLastCalledWith("/?page=2");
});

it("says when nothing matches and clears the search", async () => {
  search = "q=zzz";
  stubApi({ "GET /api/v1/organizations": [200, page([])] });
  renderWithProviders(<OrganizationList />);
  expect(await screen.findByText("Ninguna organización coincide con la búsqueda o los filtros.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Borrar la búsqueda y los filtros" }));
  expect(replace).toHaveBeenLastCalledWith("/");
});

const detail = {
  id: "o-1", name: "Clínica Norte S.L.", locale: "es", created_at: "2026-10-01T10:00:00Z", trial_ends_at: "2026-10-15T10:00:00Z", trial_ended: true,
  last_activity: null, state: "suspended", suspended_at: "2026-11-20T09:00:00Z", suspension_reason: "non_payment",
  closure: { requested_at: "2026-11-21T09:00:00Z", origin: "operator", erase_after: "2026-12-21T09:00:00Z" },
  plan: { plan: "business", default: true, addons: [], note: "", updated_at: null },
  billing: { view: "summary", legal_name: "Clínica Norte Sociedad Limitada", complete: false },
  members: { owner: 1, auditor: 2, admin: 0 }, pending_invitations: 1,
  connections: { by_provider: { m365: { active: 1, incomplete: 1 } }, health: "attention", in_use: 2, limit: 1 },
  scans: { last_30_days: { succeeded: 3 }, last_finished: "2026-11-19T09:00:00Z" }, api_keys: 0, api_calls_30_days: 12, erasure: null,
};

it("shows every metadata group; support sees the billing summary only", async () => {
  search = "id=o-1";
  stubApi({ "GET /api/v1/organizations/o-1": [200, detail] });
  renderWithProviders(<OrganizationDetailPage />);
  expect(await screen.findByRole("heading", { level: 1, name: "Clínica Norte S.L." })).toBeTruthy();
  for (const panel of ["Resumen", "Estado", "Plan", "Datos de facturación", "Uso", "Conexiones"]) expect(screen.getByRole("region", { name: panel })).toBeTruthy();
  const state = within(screen.getByRole("region", { name: "Estado" }));
  expect(state.getByText("Pago pendiente")).toBeTruthy();
  expect(state.getByText(/por Atesta/)).toBeTruthy();
  const billing = within(screen.getByRole("region", { name: "Datos de facturación" }));
  expect(billing.getByText("Clínica Norte Sociedad Limitada")).toBeTruthy();
  expect(billing.getByText("Incompletos")).toBeTruthy();
  expect(billing.queryByText("NIF")).toBeNull();
  const usage = within(screen.getByRole("region", { name: "Uso" }));
  expect(usage.getByText("1 propietario, 2 auditores externos")).toBeTruthy();
  expect(within(screen.getByRole("region", { name: "Conexiones" })).getByText("2 conexiones de 1 que permite el plan")).toBeTruthy();
  expect(within(screen.getByRole("region", { name: "Resumen" })).getByText(/solo lectura hasta que se fije un plan/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Organizaciones" }).getAttribute("href")).toBe("/");
});

it("billing staff see the full billing details; an unknown organization says so", async () => {
  search = "id=o-1";
  stubApi({ "GET /api/v1/organizations/o-1": [200, { ...detail, billing: { view: "full", legal_name: "Clínica Norte", tax_id: "B12345678",
    address_line1: "Calle Mayor 1", address_line2: null, postal_code: "28001", city: "Madrid", region: "Madrid", country: "ES",
    contact_email: "facturas@example.test", complete: true, updated_at: "2026-11-20T09:00:00Z" } }] });
  renderWithProviders(<OrganizationDetailPage />);
  const billing = within(await screen.findByRole("region", { name: "Datos de facturación" }));
  expect(billing.getByText("B12345678")).toBeTruthy();
  expect(billing.getByText("Calle Mayor 1, 28001, Madrid, Madrid, ES")).toBeTruthy();
  cleanup();
  search = "id=nope";
  stubApi({ "GET /api/v1/organizations/nope": [404, { detail: { code: "operator.not_found" } }] });
  renderWithProviders(<OrganizationDetailPage />);
  expect((await screen.findByRole("alert")).textContent).toBe("No encontramos esa organización o solicitud.");
});
