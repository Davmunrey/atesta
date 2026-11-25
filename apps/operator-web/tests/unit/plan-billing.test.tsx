// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import BillingPage from "@/app/organization/billing/page";
import PlanPage from "@/app/organization/plan/page";
import { renderAs, stubApi } from "./render";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }), useSearchParams: () => new URLSearchParams("id=o-1") }));
beforeEach(() => push.mockReset());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const org = {
  id: "o-1", name: "Clínica Norte S.L.", locale: "es", created_at: "2026-10-01T10:00:00Z", trial_ends_at: "2026-12-01T10:00:00Z", trial_ended: false,
  last_activity: null, state: "active", suspended_at: null, suspension_reason: null, closure: null, erasure: null,
  plan: { plan: "business", default: true, addons: [], note: "", updated_at: null },
  billing: { view: "full", legal_name: "Clínica Norte", tax_id: "B12345678", address_line1: "Calle Mayor 1", address_line2: null, postal_code: "28001",
    city: "Madrid", region: "Madrid", country: "ES", contact_email: "facturas@example.test", complete: true, updated_at: "2026-11-20T09:00:00Z" },
  members: {}, pending_invitations: 0, connections: { by_provider: {}, health: "ok", in_use: 2, limit: null },
  scans: { last_30_days: {}, last_finished: null }, api_keys: 0, api_calls_30_days: 0,
};
const plans = { plans: [
  { plan: "starter", connector_limit: 1, features: [] },
  { plan: "pro", connector_limit: 3, features: ["daily_monitoring", "evidence_export", "policy_ai_review"] },
  { plan: "business", connector_limit: null, features: ["daily_monitoring", "evidence_export", "policy_ai_review", "questionnaire_autofill", "trust_center"] },
], addons: ["daily_monitoring", "evidence_export", "ens_extra", "policy_ai_review", "questionnaire_autofill", "trust_center"] };

it("previews what a plan change does, warns about connections over the limit, and saves with a reason", async () => {
  const requests = stubApi({ "GET /api/v1/organizations/o-1": [200, org], "GET /api/v1/plans": [200, plans],
    "PUT /api/v1/organizations/o-1/subscription": [200, { plan: "starter", previous_plan: null, addons: ["trust_center"] }] });
  renderAs("billing", <PlanPage />);
  fireEvent.change(await screen.findByLabelText("Plan"), { target: { value: "starter" } });
  const preview = within(screen.getByRole("region", { name: "Qué cambia" }));
  expect(preview.getByText("sin límite → 1 conexión")).toBeTruthy();
  expect(preview.getByText(/Centro de confianza/)).toBeTruthy();
  expect(preview.getByRole("note").textContent).toContain("usa 2 conexiones y el nuevo plan permite 1");
  expect(screen.getByText("ens_extra").className).toBe("font-mono");
  fireEvent.click(screen.getByLabelText("Centro de confianza"));
  const save = screen.getByRole("button", { name: "Guardar el plan" }) as HTMLButtonElement;
  expect(save.disabled).toBe(true);
  fireEvent.change(screen.getByLabelText("Motivo interno"), { target: { value: " Contrato firmado " } });
  fireEvent.click(save);
  await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/organization?id=o-1"));
  const put = requests.find((r) => r.method === "PUT")!;
  expect(await put.json()).toEqual({ plan: "starter", addons: ["trust_center"], note: "", reason: "Contrato firmado" });
});

it("marks the billing field the API refuses and keeps the form", async () => {
  stubApi({ "GET /api/v1/organizations/o-1": [200, org],
    "PUT /api/v1/organizations/o-1/billing-profile": [422, { detail: { code: "operator.invalid_field", field: "tax_id" } }] });
  renderAs("admin", <BillingPage />);
  const tax = await screen.findByLabelText("NIF") as HTMLInputElement;
  expect(tax.value).toBe("B12345678");
  fireEvent.change(tax, { target: { value: "123" } });
  fireEvent.change(screen.getByLabelText("País"), { target: { value: "es" } });
  expect((screen.getByLabelText("País") as HTMLInputElement).value).toBe("ES");
  fireEvent.change(screen.getByLabelText("Motivo interno"), { target: { value: "Corrección" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar los datos de facturación" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Revisa el campo marcado: su formato no es válido.");
  expect(tax.getAttribute("aria-invalid")).toBe("true");
  expect(document.getElementById(tax.getAttribute("aria-describedby")!)!.textContent).toBe("El formato de este campo no es válido.");
  expect(document.activeElement).toBe(tax);
  expect(push).not.toHaveBeenCalled();
});

it("sends empty optional fields as null and goes back to the organization", async () => {
  const requests = stubApi({ "GET /api/v1/organizations/o-1": [200, org], "PUT /api/v1/organizations/o-1/billing-profile": [200, { changed: ["city"], updated_at: null }] });
  renderAs("billing", <BillingPage />);
  fireEvent.change(await screen.findByLabelText("Ciudad"), { target: { value: " Toledo " } });
  fireEvent.change(screen.getByLabelText("Motivo interno"), { target: { value: "Cambio de sede" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar los datos de facturación" }));
  await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/organization?id=o-1"));
  const body = await requests.find((r) => r.method === "PUT")!.json();
  expect(body).toMatchObject({ city: "Toledo", address_line2: null, tax_id: "B12345678", reason: "Cambio de sede" });
});

it("support reads that the role does not allow it, and nothing is asked of the API", async () => {
  const requests = stubApi({});
  renderAs("support", <PlanPage />);
  expect(await screen.findByText("Tu rol no permite esta acción.")).toBeTruthy();
  cleanup();
  renderAs("support", <BillingPage />);
  expect(await screen.findByText("Tu rol no permite esta acción.")).toBeTruthy();
  expect(requests.filter((r) => r.url.includes("/plans") || r.method !== "GET")).toEqual([]);
});
