// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotificationsView } from "@/components/notifications-view";
import { UnsubscribeConfirm } from "@/components/unsubscribe-confirm";
import { renderWithProviders, stubApi } from "./render";

/** Notification preferences and one-click unsubscribe (notifications spec PR 1, issue 379). */
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const membership = (role: "owner" | "admin" | "member") =>
  ({ organization_id: "primary", organization_name: "Synthetic Team", role, access_expires_on: null, closure_erase_after: null });
const base = "/api/v1/orgs/primary/notifications/preferences";
const all = [
  { kind: "connection_alert", enabled: true, can_disable: false },
  { kind: "incident_clock", enabled: true, can_disable: false },
  { kind: "scan_problem", enabled: true, can_disable: true },
  { kind: "due_digest", enabled: true, can_disable: true },
  { kind: "weekly_summary", enabled: true, can_disable: true },
];

it("lists each type, locks security notices on, and says email has not started yet", async () => {
  stubApi({ [`GET ${base}`]: [200, all] });
  renderWithProviders(<NotificationsView org={membership("owner")} />);
  const clock = await screen.findByRole("checkbox", { name: /Plazos de notificación de incidentes/ });
  expect((clock as HTMLInputElement).checked && (clock as HTMLInputElement).disabled).toBe(true);
  const alert = screen.getByRole("checkbox", { name: /Conexión revocada o con permisos de más/ }) as HTMLInputElement;
  expect(alert.checked && alert.disabled).toBe(true);
  expect(screen.getAllByText("Siempre activo: es un aviso de seguridad.")).toHaveLength(2);
  const weekly = screen.getByRole("checkbox", { name: /Resumen semanal/ }) as HTMLInputElement;
  expect(weekly.checked && !weekly.disabled).toBe(true);
  expect(screen.getByText(/Atesta aún no envía estos avisos/)).toBeTruthy();
});

it("turns a type off with a PUT and shows the saved state", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [[200, all], [200, all.map((p) => (p.kind === "weekly_summary" ? { ...p, enabled: false } : p))]],
    [`PUT ${base}`]: [200, all.map((p) => (p.kind === "weekly_summary" ? { ...p, enabled: false } : p))],
  });
  renderWithProviders(<NotificationsView org={membership("admin")} />);
  fireEvent.click(await screen.findByRole("checkbox", { name: /Resumen semanal/ }));
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "PUT")) throw new Error("no PUT"); });
  const put = requests.find((r) => r.method === "PUT")!;
  expect(await put.clone().json()).toEqual({ kind: "weekly_summary", enabled: false });
  await vi.waitFor(() => {
    expect((screen.getByRole("checkbox", { name: /Resumen semanal/ }) as HTMLInputElement).checked).toBe(false);
  });
});

it("shows a member only the due digest of their own measures", async () => {
  stubApi({ [`GET ${base}`]: [200, [{ kind: "due_digest", enabled: true, can_disable: true }]] });
  renderWithProviders(<NotificationsView org={membership("member")} />);
  expect(await screen.findByRole("checkbox", { name: /Vencimientos próximos/ })).toBeTruthy();
  expect(screen.getAllByRole("checkbox")).toHaveLength(1);
});

it("reads in English", async () => {
  stubApi({ [`GET ${base}`]: [200, all] });
  renderWithProviders(<NotificationsView org={membership("owner")} />, "en");
  expect(await screen.findByRole("checkbox", { name: /Weekly summary/ })).toBeTruthy();
  expect(screen.getAllByText("Always on: this is a security notice.")).toHaveLength(2);
});

describe("the unsubscribe page", () => {
  beforeEach(() => { window.history.replaceState(null, "", "/unsubscribe#token=sealed-token"); sessionStorage.clear(); });

  it("never acts on opening; one click POSTs the token and names what stopped", async () => {
    const requests = stubApi({ ["POST /api/v1/unsubscribe"]: [200, { kind: "weekly_summary" }] });
    renderWithProviders(<UnsubscribeConfirm />);
    const confirm = await screen.findByRole("button", { name: "Confirmar la baja" });
    expect(requests).toHaveLength(0); // opening the link changes nothing
    expect(window.location.hash).toBe(""); // the token leaves the address bar at once
    fireEvent.click(confirm);
    expect(await screen.findByText("Hecho: ya no recibirás «Resumen semanal».")).toBeTruthy();
    const post = requests[0]!;
    expect(post.method).toBe("POST");
    expect(new URL(post.url).searchParams.get("token")).toBe("sealed-token");
  });

  it("explains an invalid or expired link", async () => {
    stubApi({ ["POST /api/v1/unsubscribe"]: [400, { detail: { code: "notifications.link_invalid" } }] });
    renderWithProviders(<UnsubscribeConfirm />);
    fireEvent.click(await screen.findByRole("button", { name: "Confirmar la baja" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/caducado/);
  });

  it("says so when the link carries no token", async () => {
    window.history.replaceState(null, "", "/unsubscribe");
    stubApi({});
    renderWithProviders(<UnsubscribeConfirm />);
    expect(await screen.findByText(/El enlace no está completo/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Confirmar la baja" })).toBeNull();
  });
});
