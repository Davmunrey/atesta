// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { OrganizationDetailPage } from "@/components/organization-detail";
import { renderAs, stubApi } from "./render";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("id=o-1") }));
beforeEach(() => window.history.replaceState(null, "", "/organization?id=o-1"));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const org = {
  id: "o-1", name: "Clínica Norte S.L.", locale: "es", created_at: "2026-10-01T10:00:00Z", trial_ends_at: "2026-12-01T10:00:00Z", trial_ended: false,
  last_activity: null, state: "active", suspended_at: null, suspension_reason: null, closure: null, erasure: null,
  plan: { plan: "business", default: true, addons: [], note: "", updated_at: null }, billing: null,
  members: {}, pending_invitations: 0, connections: { by_provider: {}, health: "none", in_use: 0, limit: null },
  scans: { last_30_days: {}, last_finished: null }, api_keys: 0, api_calls_30_days: 0,
};
const GET = "GET /api/v1/organizations/o-1";
const closure = { requested_at: "2026-10-20T10:00:00Z", origin: "operator", erase_after: "2026-11-19T10:00:00Z" };

it("only admins see the actions", async () => {
  for (const role of ["billing", "support"] as const) {
    stubApi({ [GET]: [200, org] });
    renderAs(role, <OrganizationDetailPage />);
    await screen.findByRole("heading", { level: 1, name: "Clínica Norte S.L." });
    expect(screen.queryByRole("region", { name: "Suspensión" }), role).toBeNull();
    cleanup();
  }
});

it("suspends only with a reason, a code and the exact name typed", async () => {
  const requests = stubApi({ [GET]: [200, org], "POST /api/v1/organizations/o-1/suspension": [200, { suspended_at: "2026-11-25T10:00:00Z" }] });
  renderAs("admin", <OrganizationDetailPage />);
  const panel = within(await screen.findByRole("region", { name: "Suspensión" }));
  fireEvent.click(panel.getByRole("button", { name: "Suspender la organización" }));
  const form = within(panel.getByRole("form", { name: "Suspender la organización" }));
  const submit = form.getByRole("button", { name: "Suspender la organización" }) as HTMLButtonElement;
  fireEvent.change(form.getByLabelText("Motivo que verá la organización"), { target: { value: "contract_ended" } });
  fireEvent.change(form.getByLabelText("Motivo interno"), { target: { value: "Contrato terminado en octubre" } });
  fireEvent.change(form.getByLabelText("Escribe «Clínica Norte S.L.» para confirmar"), { target: { value: "clínica norte s.l." } });
  expect(submit.disabled).toBe(true);
  fireEvent.change(form.getByLabelText("Escribe «Clínica Norte S.L.» para confirmar"), { target: { value: "Clínica Norte S.L." } });
  expect(submit.disabled).toBe(false);
  fireEvent.click(submit);
  await vi.waitFor(() => expect(panel.queryByRole("form")).toBeNull());
  expect(await requests.find((r) => r.method === "POST")!.json()).toEqual(
    { reason_code: "contract_ended", reason: "Contrato terminado en octubre", confirm_name: "Clínica Norte S.L." });
});

it("asks to sign in again, and come back, when the API wants a recent sign-in", async () => {
  stubApi({ [GET]: [200, org], "POST /api/v1/organizations/o-1/closure": [401, { detail: { code: "operator.recent_auth_required" } }] });
  renderAs("admin", <OrganizationDetailPage />);
  const panel = within(await screen.findByRole("region", { name: "Exportación y cierre" }));
  fireEvent.click(panel.getByRole("button", { name: "Iniciar el cierre" }));
  fireEvent.change(panel.getByLabelText("Motivo interno"), { target: { value: "Baja" } });
  fireEvent.change(panel.getByLabelText(/para confirmar/), { target: { value: "Clínica Norte S.L." } });
  fireEvent.click(panel.getByRole("button", { name: "Iniciar el cierre" }));
  const alert = await panel.findByRole("alert");
  expect(alert.textContent).toContain("inicio de sesión de los últimos 15 minutos");
  expect(within(alert).getByRole("link", { name: "Volver a iniciar sesión" }).getAttribute("href"))
    .toBe("/auth/login?lang=es&return_to=%2Forganization%3Fid%3Do-1");
});

it("an owner's closure cannot be cancelled here; an operator closure can, and erasure can be requested", async () => {
  stubApi({ [GET]: [200, { ...org, state: "closing", closure: { ...closure, origin: "owner" } }] });
  renderAs("admin", <OrganizationDetailPage />);
  const closurePanel = within(await screen.findByRole("region", { name: "Exportación y cierre" }));
  expect(closurePanel.getByText(/solo ella puede cancelarlo/)).toBeTruthy();
  expect(closurePanel.queryByRole("button", { name: "Cancelar el cierre" })).toBeNull();
  expect(within(screen.getByRole("region", { name: "Borrado" })).getByRole("button", { name: "Pedir el borrado" })).toBeTruthy();
  cleanup();
  stubApi({ [GET]: [200, { ...org, state: "closing", closure }] });
  renderAs("admin", <OrganizationDetailPage />);
  expect(await screen.findByRole("button", { name: "Cancelar el cierre" })).toBeTruthy();
});

it("shows a pending erasure and lets another admin approve it with the name typed again", async () => {
  const erasure = { id: "e-1", state: "pending", requested_at: "2026-11-24T10:00:00Z", requested_by_me: false, approved_at: null, receipt_id: null };
  const requests = stubApi({ [GET]: [200, { ...org, state: "closing", closure, erasure }],
    "POST /api/v1/erasure-requests/e-1/approval": [409, { detail: { code: "operator.erasure_expired" } }] });
  renderAs("admin", <OrganizationDetailPage />);
  const panel = within(await screen.findByRole("region", { name: "Borrado" }));
  expect(panel.getByText("Pendiente de aprobación")).toBeTruthy();
  expect(panel.getByText(/por otra persona administradora/)).toBeTruthy();
  fireEvent.click(panel.getByRole("button", { name: "Aprobar el borrado" }));
  fireEvent.change(panel.getByLabelText("Motivo interno"), { target: { value: "Revisado" } });
  fireEvent.change(panel.getByLabelText(/para confirmar/), { target: { value: "Clínica Norte S.L." } });
  fireEvent.click(panel.getByRole("button", { name: "Aprobar el borrado" }));
  expect((await panel.findByRole("alert")).textContent).toContain("ha caducado");
  expect(await requests.find((r) => r.method === "POST")!.json()).toEqual({ confirm_name: "Clínica Norte S.L.", reason: "Revisado" });
  expect(panel.getByRole("button", { name: "Cancelar la solicitud de borrado" })).toBeTruthy();
});

it("an executed erasure names its receipt and offers nothing more", async () => {
  const erasure = { id: "e-1", state: "executed", requested_at: "2026-10-01T10:00:00Z", requested_by_me: true, approved_at: "2026-10-02T10:00:00Z", receipt_id: "r-9" };
  stubApi({ [GET]: [200, { ...org, state: "closing", closure, erasure }] });
  renderAs("admin", <OrganizationDetailPage />);
  const panel = within(await screen.findByRole("region", { name: "Borrado" }));
  expect(panel.getByText("Los datos se borraron. Recibo: r-9")).toBeTruthy();
  expect(panel.queryByRole("button")).toBeNull();
});
