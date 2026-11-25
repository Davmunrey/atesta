// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ErasedOrganizations } from "@/components/erased";
import { OperationsLog } from "@/components/operations-log";
import { Team } from "@/components/team";
import { renderAs, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const staff = [
  { id: "s-1", email: "admin@atesta.test", role: "admin", disabled_at: null },
  { id: "s-2", email: "support@atesta.test", role: "support", disabled_at: null },
  { id: "s-3", email: "former@atesta.test", role: "support", disabled_at: "2026-11-01T10:00:00Z" },
];

it("lists the team; one's own row has no actions; a role change takes a reason", async () => {
  const requests = stubApi({ "GET /api/v1/staff": [200, staff], "PATCH /api/v1/staff/s-2": [200, { ...staff[1], role: "billing" }] });
  renderAs("admin", <Team />);
  const table = within(await screen.findByRole("region", { name: "Personas del equipo" }));
  const mine = table.getByRole("row", { name: /admin@atesta.test/ });
  expect(within(mine).getByText("Tú")).toBeTruthy();
  expect(within(mine).queryByRole("button")).toBeNull();
  expect(within(table.getByRole("row", { name: /former@atesta.test/ })).getByText("Desactivado")).toBeTruthy();
  fireEvent.click(within(table.getByRole("row", { name: /support@atesta.test/ })).getByRole("button", { name: "Gestionar" }));
  fireEvent.click(screen.getByRole("button", { name: "Cambiar el rol de support@atesta.test" }));
  const form = within(screen.getByRole("form", { name: "Cambiar el rol de support@atesta.test" }));
  fireEvent.change(form.getByLabelText("Nuevo rol"), { target: { value: "billing" } });
  fireEvent.change(form.getByLabelText("Motivo interno"), { target: { value: "Se ocupa de la facturación" } });
  fireEvent.click(form.getByRole("button", { name: "Cambiar el rol" }));
  await vi.waitFor(() => expect(requests.some((r) => r.method === "PATCH")).toBe(true));
  expect(await requests.find((r) => r.method === "PATCH")!.json()).toEqual({ role: "billing", reason: "Se ocupa de la facturación" });
});

it("shows the API's refusal when the last admin would be lost", async () => {
  stubApi({ "GET /api/v1/staff": [200, staff], "PATCH /api/v1/staff/s-2": [409, { detail: { code: "operator.last_admin" } }] });
  renderAs("admin", <Team />);
  const row = await screen.findByRole("row", { name: /support@atesta.test/ });
  fireEvent.click(within(row).getByRole("button", { name: "Gestionar" }));
  fireEvent.click(screen.getByRole("button", { name: "Desactivar a support@atesta.test" }));
  fireEvent.change(screen.getByLabelText("Motivo interno"), { target: { value: "Baja" } });
  fireEvent.click(screen.getByRole("button", { name: "Desactivar el acceso" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Debe quedar al menos una persona administradora activa.");
});

it("reads the operator trail with staff emails, sentences, reasons and metadata, and filters it", async () => {
  const row = { id: "e-1", occurred_at: "2026-11-25T10:00:00Z", staff_id: "s-1", staff_role: "admin", action: "operator.plan_changed",
    organization_id: "0d41457a-06a2-4d42-98e4-6c5908271f34", target_id: null, reason: "Contrato firmado", request_id: "r", metadata: { plan: "pro", previous_plan: "business" } };
  const runner = { ...row, id: "e-2", staff_id: null, staff_role: null, action: "erasure.executed", reason: null, metadata: {} };
  const requests = stubApi({ "GET /api/v1/staff": [200, staff], "GET /api/v1/operator-events": [200, { rows: [row, runner], total: 2, page: 1, page_size: 50 }] });
  renderAs("admin", <OperationsLog />);
  const table = within(await screen.findByRole("region", { name: "Operaciones" }));
  const first = within(table.getByRole("row", { name: /Cambió el plan/ }));
  for (const text of ["admin@atesta.test", "Contrato firmado", "plan: pro · previous_plan: business"]) expect(first.getByText(text)).toBeTruthy();
  expect(first.getByRole("link", { name: "0d41457a" }).getAttribute("href")).toBe("/organization?id=0d41457a-06a2-4d42-98e4-6c5908271f34");
  expect(within(table.getByRole("row", { name: /Se ejecutó el borrado/ })).getByText("Proceso de borrado")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Acción"), { target: { value: "staff.disabled" } });
  await vi.waitFor(() => expect(new URL(requests.at(-1)!.url).searchParams.get("action")).toBe("staff.disabled"));
  fireEvent.change(screen.getByLabelText("Organización"), { target: { value: "not-an-id" } });
  expect((screen.getByRole("button", { name: "Filtrar" }) as HTMLButtonElement).disabled).toBe(true);
});

it("lists erasure receipts by id, dates and rows; other roles get nothing", async () => {
  stubApi({ "GET /api/v1/erasure-receipts": [200, { rows: [{ id: "r-1", organization_id: "7e5a5e00-0000-4000-8000-000000000001",
    closure_requested_at: "2026-10-01T10:00:00Z", erased_at: "2026-11-01T10:00:00Z", rows: 1234 }], total: 1, page: 1, page_size: 50 }] });
  renderAs("admin", <ErasedOrganizations />);
  const row = within(await screen.findByRole("row", { name: /7e5a5e00/ }));
  expect(row.getByText("1234")).toBeTruthy();
  cleanup();
  const requests = stubApi({});
  renderAs("billing", <ErasedOrganizations />);
  expect(screen.getByText("Tu rol no permite esta acción.")).toBeTruthy();
  expect(requests).toEqual([]);
});
