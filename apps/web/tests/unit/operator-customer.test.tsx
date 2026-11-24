// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AppLayout from "@/app/(app)/app/layout";
import { ActivityView } from "@/components/activity-view";
import { SettingsView } from "@/components/settings-view";
import { overview } from "../fixtures/overview";
import { renderWithProviders, stubApi } from "./render";

vi.mock("next/navigation", () => ({
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ push: (url: string) => window.history.pushState(null, "", url) }),
}));

type Role = "owner" | "admin" | "member";
const membership = (role: Role, extra: Record<string, unknown> = {}) => ({
  organization_id: "primary", organization_name: "Synthetic Team", role, access_expires_on: null, closure_erase_after: null, ...extra,
});
const suspended = { suspended: true, suspended_at: "2026-11-20T09:00:00Z", suspension_reason: "non_payment" };
const billing = {
  legal_name: "Ejemplo S.L.", tax_id: "B00000000", address_line1: "Calle Mayor 1", address_line2: null, postal_code: "28001",
  city: "Madrid", region: "Madrid", country: "ES", contact_email: "facturas@example.test", complete: true, updated_at: "2026-11-20T09:00:00Z",
};

beforeEach(() => { localStorage.clear(); window.history.replaceState(null, "", "/app/org?org=primary"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function shell(member: object, routes: Record<string, [number, unknown]> = {}) {
  const requests = stubApi({
    "GET /api/v1/me": [200, { id: "u", email: "c@example.test", email_verified: true, locale: "es", memberships: [member] }],
    "GET /api/v1/orgs/primary/overview": [200, overview],
    ...routes,
  });
  renderWithProviders(<AppLayout><h1>Page</h1></AppLayout>);
  return requests;
}

// --- suspension -------------------------------------------------------------------------------

it("replaces every organization page for a suspended member, without the organization navigation", async () => {
  const requests = shell(membership("member", { ...suspended, suspension_reason: null }));
  expect(await screen.findByRole("heading", { level: 1, name: "Organización suspendida" })).toBeTruthy();
  expect(screen.getByText(/El acceso a Synthetic Team está en pausa desde el 20 de noviembre de 2026/)).toBeTruthy();
  expect(screen.getByText("Para saber más, habla con la persona propietaria de la organización.")).toBeTruthy();
  expect(screen.queryByText("Page")).toBeNull();
  expect(screen.queryByRole("navigation", { name: "Secciones de la organización" })).toBeNull();
  expect(screen.queryByRole("combobox", { name: "Buscar en Atesta" })).toBeNull();
  expect(screen.queryByText(/Motivo/)).toBeNull();
  expect(requests.some((r) => new URL(r.url).pathname.endsWith("/trial"))).toBe(false);
});

it("shows owners the reason, the export and closure, and their billing details", async () => {
  shell(membership("owner", suspended), { "GET /api/v1/orgs/primary/billing-profile": [200, billing] });
  expect(await screen.findByText("Motivo: pago pendiente. Para reactivarla, escribe a hello@atesta.cloud.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Exportar los datos" }).getAttribute("href")).toBe("/api/v1/orgs/primary/export");
  expect(screen.getByRole("link", { name: "Cerrar la organización" }).getAttribute("href")).toBe("/app/settings?org=primary");
  const details = await screen.findByRole("region", { name: "Datos de facturación" });
  expect(await within(details).findByText("Ejemplo S.L.")).toBeTruthy();
  expect(within(details).getByText("España")).toBeTruthy();
});

it("lets a suspended owner reach Ajustes, without the language they could not save", async () => {
  window.history.replaceState(null, "", "/app/settings?org=primary");
  shell(membership("owner", suspended));
  renderWithProviders(<SettingsView org={membership("owner", suspended)} />);
  expect(await screen.findByRole("link", { name: "Descargar exportación" })).toBeTruthy();
  expect(screen.queryByLabelText("Idioma de los avisos por email")).toBeNull();
});

// --- trial ------------------------------------------------------------------------------------

it("tells owners and admins when the trial ends", async () => {
  shell(membership("admin"), { "GET /api/v1/orgs/primary/trial": [200, { ends_at: "2026-12-01T10:00:00Z", ended: false }] });
  expect(await screen.findByText("Prueba de 14 días: termina el 1 de diciembre de 2026.")).toBeTruthy();
});

it("does not show the trial date to members while it runs", async () => {
  shell(membership("member"), { "GET /api/v1/orgs/primary/trial": [200, { ends_at: "2026-12-01T10:00:00Z", ended: false }] });
  await screen.findByRole("navigation", { name: "Secciones de la organización" });
  await new Promise((r) => setTimeout(r, 0));
  expect(screen.queryByText(/Prueba de 14 días/)).toBeNull();
});

it("tells everyone the organization is read-only once the trial has ended", async () => {
  shell(membership("member"), { "GET /api/v1/orgs/primary/trial": [200, { ends_at: "2026-11-10T10:00:00Z", ended: true }] });
  const note = await screen.findByText(/La prueba de 14 días terminó el 10 de noviembre de 2026\. La organización es de solo lectura/);
  expect(note.closest(".notice")?.getAttribute("data-severity")).toBe("overdue");
  expect(note.textContent).toContain("hello@atesta.cloud");
});

it("says nothing about a trial once a plan is set", async () => {
  shell(membership("owner"), { "GET /api/v1/orgs/primary/trial": [200, { ends_at: null, ended: false }] });
  await screen.findByRole("navigation", { name: "Secciones de la organización" });
  await new Promise((r) => setTimeout(r, 0));
  expect(screen.queryByText(/prueba de 14 días/i)).toBeNull();
});

// --- Ajustes: billing details and the operator closure ---------------------------------------

it("shows the billing details read-only in Ajustes", async () => {
  stubApi({ "GET /api/v1/orgs/primary/billing-profile": [200, { ...billing, address_line2: "Piso 2", tax_id: null }] });
  renderWithProviders(<SettingsView org={membership("owner")} />);
  const details = await screen.findByRole("region", { name: "Datos de facturación" });
  expect(await within(details).findByText("Calle Mayor 1, Piso 2")).toBeTruthy();
  expect(within(details).getByText("Sin registrar")).toBeTruthy();
  expect(within(details).queryByRole("textbox")).toBeNull();
});

it("explains that Atesta has not recorded billing details yet", async () => {
  stubApi({ "GET /api/v1/orgs/primary/billing-profile": [404, { detail: { code: "billing.no_profile" } }] });
  renderWithProviders(<SettingsView org={membership("owner")} />);
  expect(await screen.findByText("Atesta aún no ha registrado tus datos de facturación.")).toBeTruthy();
});

it("shows an operator closure without a cancel button, and who to write to", () => {
  stubApi({});
  renderWithProviders(<SettingsView org={membership("owner", { closure_erase_after: "2026-12-23T10:00:00Z", closure_origin: "operator" })} />);
  expect(screen.getByText("El cierre lo inició Atesta. Para cancelarlo, escribe a hello@atesta.cloud.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Cancelar el cierre" })).toBeNull();
});

// --- Activity ---------------------------------------------------------------------------------

it("shows operator actions as the Atesta team, never a person", async () => {
  stubApi({ "GET /api/v1/orgs/primary/activity": [200, { days: 30, daily: [], events: [
    { occurred_at: "2026-11-20T09:00:00Z", actor_email: null, actor_kind: "atesta", action: "operator.plan_changed", target_type: "organization", target_id: "primary" },
    { occurred_at: "2026-11-19T09:00:00Z", actor_email: null, actor_kind: "system", action: "scan.failed", target_type: "scan", target_id: "x" },
  ] }] });
  renderWithProviders(<ActivityView org={membership("owner")} />);
  const row = (await screen.findByText("Cambió el plan")).closest("tr")!;
  expect(within(row).getByText("Equipo de Atesta")).toBeTruthy();
  expect(screen.getByText("Sistema")).toBeTruthy();
});
