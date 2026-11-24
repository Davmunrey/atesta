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
  created_at: "2026-11-20T10:00:00Z", verified_at: null, consented: false, tenant_id: null,
  google_subject_set: false, primary_domain: null, ...over,
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

it("adds a connection of the chosen service, named after it when the name is left empty", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [[200, []], [200, [conn({})]]],
    [`POST ${base}`]: [201, conn({})],
  });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  expect(await screen.findByText(/Aún no hay conexiones/)).toBeTruthy();
  expect(screen.queryByText("Próximamente")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Añadir" }));
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "POST")) throw new Error("no POST"); });
  expect(await requests.find((r) => r.method === "POST")!.clone().json()).toEqual({ provider: "m365", display_name: "Microsoft 365" });
  fireEvent.change(screen.getByRole("combobox", { name: "Servicio" }), { target: { value: "google_workspace" } });
  fireEvent.click(screen.getByRole("button", { name: "Añadir" }));
  await vi.waitFor(() => { if (requests.filter((r) => r.method === "POST").length < 2) throw new Error("no second POST"); });
  expect(await requests.filter((r) => r.method === "POST")[1]!.clone().json()).toEqual({ provider: "google_workspace", display_name: "Google Workspace" });
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

// Google Workspace (web-connections spec, issue 425).
const google = (over: object) => conn({ id: "g1", provider: "google_workspace", display_name: "Contoso Workspace", allowlist_version: "google-v1", ...over });
const SCAN_SCOPES = ["https://www.googleapis.com/auth/admin.directory.customer.readonly", "https://www.googleapis.com/auth/admin.directory.user.readonly"];
const VERIFIER_SCOPES = ["https://www.googleapis.com/auth/admin.reports.audit.readonly"];
const googleDetail = (over: object, ids = true) => ({
  ...google(over), google_client_id: ids ? "111111111111111111111" : null, google_verifier_client_id: ids ? "222222222222222222222" : null,
  expected_access: { permissions: [], scan_scopes: SCAN_SCOPES, verifier_scopes: VERIFIER_SCOPES }, last_verification: null,
});

it.each([
  ["pending_provisioning", false, "Pendiente de preparar", ["Desconectar Contoso Workspace"]],
  ["pending_setup", false, "Pendiente de conectar", ["Desconectar Contoso Workspace"]],
  ["pending_setup", true, "Pendiente de verificar", ["Verificar Contoso Workspace", "Desconectar Contoso Workspace"]],
  ["incomplete", true, "Permisos incompletos", ["Verificar Contoso Workspace", "Desconectar Contoso Workspace"]],
  ["verifying", true, "Verificando", ["Desconectar Contoso Workspace"]],
  ["active", true, "Activa", ["Escanear ahora Contoso Workspace", "Desconectar Contoso Workspace"]],
] as const)("a Google connection in %s (super admin named %s) reads %s with its actions", async (status, named, label, actions) => {
  stubApi({
    [`GET ${base}`]: [200, [google({ status, google_subject_set: named, primary_domain: named ? "example.es" : null })]],
    [`GET ${base}/g1`]: [200, googleDetail({ status }, status !== "pending_provisioning")],
  });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  const line = await screen.findByRole("row", { name: /Contoso Workspace/ });
  expect(within(line).getByText(label)).toBeTruthy();
  const named_ = within(line).getAllByRole("button").filter((b) => b.hasAttribute("aria-label"));
  expect(named_.map((b) => b.getAttribute("aria-label"))).toEqual(actions);
});

it("tells an admin where to authorize both clients, with exact scopes to copy", async () => {
  stubApi({
    [`GET ${base}`]: [200, [google({})]],
    [`GET ${base}/g1`]: [200, googleDetail({})],
  });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  const details = (await screen.findByText("Acceso en Google Workspace")).closest("details")!;
  expect(details.open).toBe(true); // onboarding: the steps are the next thing to do
  expect(await screen.findByText("111111111111111111111")).toBeTruthy();
  expect(screen.getByText("222222222222222222222")).toBeTruthy();
  expect(screen.getByText(SCAN_SCOPES.join(","))).toBeTruthy(); // exactly, comma-separated
  expect(screen.getByText(VERIFIER_SCOPES.join(","))).toBeTruthy();
  expect(screen.getByText(/Gestionar la delegación de todo el dominio/)).toBeTruthy();
  expect(within(screen.getByRole("row", { name: /Contoso Workspace/ })).getByText("Aún sin dominio")).toBeTruthy();
  for (const name of ["Copiar el ID del cliente de lectura", "Copiar los ámbitos del cliente de lectura",
    "Copiar el ID del cliente de comprobación", "Copiar los ámbitos del cliente de comprobación"]) {
    expect(screen.getByRole("button", { name })).toBeTruthy();
  }
});

it("says Atesta is still preparing the accounts before provisioning", async () => {
  stubApi({
    [`GET ${base}`]: [200, [google({ status: "pending_provisioning" })]],
    [`GET ${base}/g1`]: [200, googleDetail({ status: "pending_provisioning" }, false)],
  });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  expect(await screen.findByText(/Atesta está preparando las cuentas de solo lectura/)).toBeTruthy();
  expect(screen.queryByText("111111111111111111111")).toBeNull();
  expect(screen.getByRole("textbox", { name: "Correo del superadministrador" })).toBeTruthy(); // can name it already
});

it("names the super admin, with the primary domain only for a secondary domain", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [[200, [google({})]], [200, [google({ google_subject_set: true, primary_domain: "example.es" })]]],
    [`GET ${base}/g1`]: [200, googleDetail({})],
    [`PUT ${base}/g1/google`]: [200, google({ google_subject_set: true, primary_domain: "example.es" })],
  });
  renderWithProviders(<ConnectionsView org={membership("admin")} />);
  const email = await screen.findByRole("textbox", { name: "Correo del superadministrador" });
  expect(screen.queryByRole("textbox", { name: "Dominio principal" })).toBeNull();
  expect(screen.getByText(/Te recomendamos un superadministrador que ya exista/)).toBeTruthy();
  fireEvent.change(email, { target: { value: "it@second.es" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "Está en un dominio secundario" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Dominio principal" }), { target: { value: "example.es" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "PUT")) throw new Error("no PUT"); });
  expect(await requests.find((r) => r.method === "PUT")!.clone().json()).toEqual({ email: "it@second.es", primary_domain: "example.es" });
  expect(await screen.findByText("Superadministrador indicado (dominio example.es).")).toBeTruthy();
  expect(screen.queryByText("it@second.es")).toBeNull(); // the email is never shown back
});

it("shows the primary domain until the customer id is pinned, and Google's wait while verifying", async () => {
  stubApi({
    [`GET ${base}`]: [200, [google({ status: "verifying", google_subject_set: true, primary_domain: "example.es" })]],
    [`GET ${base}/g1`]: [200, googleDetail({ status: "verifying" })],
  });
  renderWithProviders(<ConnectionsView org={membership("member")} />);
  const line = await screen.findByRole("row", { name: /Contoso Workspace/ });
  expect(within(line).getByText("example.es")).toBeTruthy();
  expect(within(line).getByText(/Google puede tardar hasta 24 horas/)).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "Correo del superadministrador" })).toBeNull(); // admins only
});

it("names the Google step when disconnecting", async () => {
  stubApi({ [`GET ${base}`]: [200, [google({ status: "active", tenant_id: "C0fixture1", google_subject_set: true, primary_domain: "example.es" })]] });
  renderWithProviders(<ConnectionsView org={membership("owner")} />);
  fireEvent.click(await screen.findByRole("button", { name: "Desconectar Contoso Workspace" }));
  expect(screen.getByText(/borra las dos entradas de Atesta en la delegación de todo el dominio/)).toBeTruthy();
});

it("reads the Google steps in English", async () => {
  stubApi({ [`GET ${base}`]: [200, [google({})]], [`GET ${base}/g1`]: [200, googleDetail({})] });
  renderWithProviders(<ConnectionsView org={membership("admin")} />, "en");
  expect(await screen.findByText("Access in Google Workspace")).toBeTruthy();
  expect(await screen.findByRole("textbox", { name: "Super admin email" })).toBeTruthy();
});
