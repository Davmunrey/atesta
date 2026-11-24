// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConnectionsView } from "@/components/connections-view";
import { isMicrosoftLogin } from "@/lib/api/connections";
import { renderWithProviders, stubApi } from "./render";

/** web-connections spec (#365, #366): the Microsoft 365 connections screen. */
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const membership = (role: "owner" | "admin" | "member") =>
  ({ organization_id: "primary", organization_name: "Synthetic Team", role, access_expires_on: null, closure_erase_after: null });
const base = "/api/v1/orgs/primary/connections";
const TENANT = "11111111-2222-4333-8444-555555555555";
const conn = (over: object) => ({
  id: "c1", provider: "m365", status: "pending_setup", display_name: "Contoso M365", allowlist_version: "m365-v1",
  created_at: "2026-11-20T10:00:00Z", verified_at: null, consented: false, tenant_id: null, ...over,
});
const LOGIN = "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize?client_id=x";

it.each([
  ["pending_setup", false, "Pendiente de conectar", ["Conectar Contoso M365 con Microsoft", "Desconectar Contoso M365"]],
  ["pending_setup", true, "Pendiente de verificar", ["Verificar Contoso M365", "Conectar de nuevo Contoso M365", "Desconectar Contoso M365"]],
  ["incomplete", true, "Permisos incompletos", ["Verificar Contoso M365", "Conectar de nuevo Contoso M365", "Desconectar Contoso M365"]],
  ["verifying", true, "Verificando", ["Desconectar Contoso M365"]],
  ["active", true, "Activa", ["Escanear ahora Contoso M365", "Desconectar Contoso M365"]],
] as const)("in %s (consented %s) an admin sees %s and its actions", async (status, consented, label, actions) => {
  stubApi({ [`GET ${base}`]: [200, [conn({ status, consented, tenant_id: consented ? TENANT : null })]] });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  const line = await screen.findByRole("row", { name: /Contoso M365/ });
  expect(within(line).getByText(label)).toBeTruthy();
  const named = within(line).getAllByRole("button").filter((b) => b.hasAttribute("aria-label"));
  expect(named.map((b) => b.getAttribute("aria-label"))).toEqual(actions);
  if (consented) expect(within(line).getByText(TENANT)).toBeTruthy();
});

it("shows members the state and no action", async () => {
  stubApi({ [`GET ${base}`]: [200, [conn({ status: "active", consented: true, tenant_id: TENANT, verified_at: "2026-11-22T09:30:00Z" })]] });
  renderWithProviders(<ConnectionsView org={membership("member")} />);
  const line = await screen.findByRole("row", { name: /Contoso M365/ });
  expect(within(line).getByText("Activa")).toBeTruthy();
  expect(within(line).queryAllByRole("button")).toHaveLength(0); // no action
  expect(screen.getByText("Permisos que concedes").tagName).toBe("SUMMARY"); // reading is for everyone
  expect(screen.queryByRole("button", { name: "Añadir" })).toBeNull();
});

it.each([
  ["active", "done"], ["verifying", "pending"], ["pending_setup", "pending"], ["incomplete", "missing"],
  ["over_privileged", "overdue"], ["revoked", "overdue"],
] as const)("draws the %s state with the shared severity (%s)", async (status, severity) => {
  stubApi({ [`GET ${base}`]: [200, [conn({ status, consented: true, tenant_id: TENANT })]] });
  renderWithProviders(<ConnectionsView org={membership("member")} />);
  const line = await screen.findByRole("row", { name: /Contoso M365/ });
  expect(line.querySelector(".badge")?.getAttribute("data-severity")).toBe(severity);
});

it("goes to Microsoft only when the API answers with Microsoft's sign-in URL", async () => {
  const navigate = vi.fn();
  stubApi({
    [`GET ${base}`]: [200, [conn({})]],
    [`POST ${base}/c1/m365/signin`]: [[200, { authorize_url: "https://evil.example/authorize" }], [200, { authorize_url: LOGIN }]],
  });
  renderWithProviders(<ConnectionsView org={membership("owner")} navigate={navigate} />);
  fireEvent.click(await screen.findByRole("button", { name: "Conectar Contoso M365 con Microsoft" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(navigate).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Conectar Contoso M365 con Microsoft" }));
  await vi.waitFor(() => { expect(navigate).toHaveBeenCalledWith(LOGIN); });
});

it("accepts only https://login.microsoftonline.com as the sign-in origin", () => {
  expect(isMicrosoftLogin(LOGIN)).toBe(true);
  for (const url of ["http://login.microsoftonline.com/x", "https://login.microsoftonline.com.evil.example/x",
    "https://evil.example/?https://login.microsoftonline.com", "javascript:alert(1)", "/relative", ""]) {
    expect(isMicrosoftLogin(url), url).toBe(false);
  }
});

it("verifies a consented connection", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [[200, [conn({ consented: true, tenant_id: TENANT })]], [200, [conn({ status: "verifying", consented: true, tenant_id: TENANT })]]],
    [`POST ${base}/c1/verify`]: [202, { id: "s1", status: "queued", trigger: "activation" }],
  });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  fireEvent.click(await screen.findByRole("button", { name: "Verificar Contoso M365" }));
  expect(await screen.findByText("Verificando")).toBeTruthy();
  expect(requests.filter((r) => r.method === "POST").map((r) => new URL(r.url).pathname)).toEqual([`${base}/c1/verify`]);
});

it("asks before disconnecting, then disconnects", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [[200, [conn({ status: "active", consented: true, tenant_id: TENANT })]], [200, []]],
    [`DELETE ${base}/c1`]: [200, conn({ status: "disconnected" })],
  });
  renderWithProviders(<ConnectionsView org={membership("owner")} />);
  const ask = await screen.findByRole("button", { name: "Desconectar Contoso M365" });
  expect(ask.className).toBe("dashboard-button"); // the members pattern (DESIGN.md, Buttons)
  fireEvent.click(ask);
  expect(requests.some((r) => r.method === "DELETE")).toBe(false);
  expect(screen.getByText(/¿Desconectar Contoso M365\?/).closest(".confirm-row")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Cancelar" }).className).toBe("dashboard-button");
  const confirm = screen.getByRole("button", { name: "Sí, desconectar" });
  expect(confirm.className).toBe("button-danger");
  fireEvent.click(confirm);
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "DELETE")) throw new Error("no DELETE"); });
});

it("lists exactly the read-only permissions the API expects, and what the last check found", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [200, [conn({ status: "over_privileged", consented: true, tenant_id: TENANT })]],
    [`GET ${base}/c1`]: [200, {
      ...conn({ status: "over_privileged", consented: true, tenant_id: TENANT }), google_client_id: null, google_verifier_client_id: null,
      expected_access: { permissions: ["AuditLog.Read.All", "User.Read.All"], scan_scopes: [], verifier_scopes: [] },
      last_verification: { missing: [], extra: ["User.ReadWrite.All"], limits: [] },
    }],
  });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  const details = (await screen.findByText("Permisos que concedes")).closest("details")!;
  expect(details.className).toContain("row-section"); // the shared disclosure (DESIGN.md)
  expect(details.open).toBe(false);
  expect(requests.some((r) => new URL(r.url).pathname === `${base}/c1`)).toBe(false); // fetched on open
  details.open = true;
  fireEvent(details, new Event("toggle"));
  expect(await screen.findByText("AuditLog.Read.All")).toBeTruthy();
  expect(screen.getByText("User.Read.All")).toBeTruthy();
  expect(screen.getByText(/2 permisos de Microsoft Graph, todos de solo lectura/)).toBeTruthy();
  expect(screen.getByText("User.ReadWrite.All")).toBeTruthy();
});

it("adds a Microsoft 365 connection and shows Google Workspace as coming soon", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [[200, []], [200, [conn({})]]],
    [`POST ${base}`]: [201, conn({})],
  });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  expect(await screen.findByText(/Aún no hay conexiones/)).toBeTruthy();
  const google = screen.getByText("Google Workspace").closest("li")!;
  expect(within(google).getByText("Próximamente")).toBeTruthy();
  expect(within(google).queryAllByRole("button")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "Añadir" }));
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "POST")) throw new Error("no POST"); });
  const post = requests.find((r) => r.method === "POST")!;
  expect(await post.clone().json()).toEqual({ provider: "m365", display_name: "Microsoft 365" });
});

it("after consent, marks the connection and names the next step", async () => {
  stubApi({ [`GET ${base}`]: [200, [conn({ consented: true, tenant_id: TENANT })]] });
  renderWithProviders(<ConnectionsView org={membership("admin")} focus="c1" />);
  expect(await screen.findByText("Permisos concedidos para Contoso M365. Verifica la conexión para empezar a escanear.")).toBeTruthy();
  expect(screen.getByRole("row", { name: /Contoso M365/ }).getAttribute("aria-current")).toBe("true");
});

it("shows a returned error code's message, and the generic one for an unknown code", async () => {
  stubApi({ [`GET ${base}`]: [200, [conn({})]] });
  renderWithProviders(<ConnectionsView org={membership("admin")} focus="c1" error="connections.consent_denied" />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/consentimiento/i);
  cleanup();
  stubApi({ [`GET ${base}`]: [200, [conn({})]] });
  renderWithProviders(<ConnectionsView org={membership("admin")} error="<img src=x onerror=alert(1)>" />);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).not.toContain("<img");
  expect(alert.innerHTML).not.toContain("onerror");
});

it("reads in English", async () => {
  stubApi({ [`GET ${base}`]: [200, [conn({ status: "active", consented: true, tenant_id: TENANT })]] });
  renderWithProviders(<ConnectionsView org={membership("owner")} />, "en");
  expect(await screen.findByText("Active")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Scan now Contoso M365" })).toBeTruthy();
  expect(screen.getByText("Never")).toBeTruthy();
});
