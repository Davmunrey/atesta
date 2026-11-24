// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { IntegrationsView } from "@/components/integrations-view";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const base = "/api/v1/orgs/primary/api-tokens";
const TOKEN = "atesta_" + "k".repeat(43);
const row = (over: object) => ({
  id: "t1", name: "GitHub Actions", prefix: "atesta_kkkkk", scopes: ["evidence:write"], rate_limit_per_minute: 60, read_only: false, created_by_email: "ana@example.com",
  created_at: "2026-11-01T10:00:00Z", expires_at: "2099-01-30T10:00:00Z", last_used_at: null, revoked_at: null, ...over,
});

it("shows a new token once, with a curl example, and never lists it again", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [[200, []], [200, [row({})]]],
    [`POST ${base}`]: [201, { ...row({}), token: TOKEN }],
  });
  renderWithProviders(<IntegrationsView org={owner} />);
  fireEvent.change(await screen.findByLabelText("Nombre"), { target: { value: "GitHub Actions" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "Registrar evidencias" }));
  fireEvent.click(screen.getByRole("button", { name: "Crear el token" }));
  expect(await screen.findByDisplayValue(TOKEN)).toBeTruthy();
  expect((screen.getByLabelText("Ejemplo de uso") as HTMLTextAreaElement).value).toContain(`Authorization: Bearer ${TOKEN}`);
  const post = requests.find((r) => r.method === "POST")!;
  expect(await post.clone().json()).toEqual({ name: "GitHub Actions", expires_in_days: 90, scopes: ["evidence:write"], rate_limit_per_minute: 60 });
  const table = await screen.findByRole("table");
  expect(within(table).queryByText(TOKEN)).toBeNull();
  expect(within(table).getByText("atesta_kkkkk…")).toBeTruthy();
});

it("shows revoked and expired tokens, and revokes an active one", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [200, [
      row({}),
      row({ id: "t2", name: "Copias", revoked_at: "2026-11-10T10:00:00Z" }),
      row({ id: "t3", name: "Escáner", expires_at: "2026-11-02T10:00:00Z", last_used_at: "2026-11-01T12:00:00Z" }),
    ]],
    [`DELETE ${base}/t1`]: [204, null],
  });
  renderWithProviders(<IntegrationsView org={owner} />);
  expect(await screen.findByText("Revocado el 10 nov 2026")).toBeTruthy();
  expect(screen.getByText("Caducó el 2 nov 2026")).toBeTruthy();
  expect(screen.getAllByRole("button", { name: /^Revocar el token/ })).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Revocar el token GitHub Actions" }));
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "DELETE")) throw new Error("no DELETE"); });
});

it("reads in English", async () => {
  stubApi({ [`GET ${base}`]: [200, [row({})]] });
  renderWithProviders(<IntegrationsView org={owner} />, "en");
  expect(await screen.findByText("Active until Jan 30, 2099")).toBeTruthy();
  // Only in the token's row: the last use is not a headline figure (console-unification spec).
  expect(screen.getAllByText("Never")).toHaveLength(1);
  expect(screen.getByText("At least one token is active.")).toBeTruthy();
});

it("asks for at least one permission and offers a read-only preset", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [200, []],
    [`POST ${base}`]: [201, { ...row({ scopes: ["compliance:read", "incidents:read"], read_only: true, rate_limit_per_minute: 30 }), token: TOKEN }],
  });
  renderWithProviders(<IntegrationsView org={owner} />);
  fireEvent.change(await screen.findByLabelText("Nombre"), { target: { value: "Agente" } });
  for (const box of screen.getAllByRole("checkbox")) expect((box as HTMLInputElement).checked).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Crear el token" }));
  expect(await screen.findByText("Elige al menos un permiso.")).toBeTruthy();
  expect(requests.some((r) => r.method === "POST")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Marcar solo lectura" }));
  expect(screen.getByRole("group", { name: "Leer" })).toBeTruthy();
  const write = within(screen.getByRole("group", { name: "Escribir" })).getAllByRole("checkbox") as HTMLInputElement[];
  expect(write.every((box) => !box.checked)).toBe(true);
  fireEvent.change(screen.getByLabelText("Límite de peticiones"), { target: { value: "30" } });
  fireEvent.click(screen.getByRole("button", { name: "Crear el token" }));
  await vi.waitFor(() => { if (!requests.some((r) => r.method === "POST")) throw new Error("no POST"); });
  const post = requests.find((r) => r.method === "POST")!;
  expect(await post.clone().json()).toEqual({ name: "Agente", expires_in_days: 90, scopes: ["compliance:read", "incidents:read"], rate_limit_per_minute: 30 });
});

it("lists each token's permissions and limit, and shows its usage on demand", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [200, [row({ scopes: ["compliance:read", "incidents:read"], read_only: true, rate_limit_per_minute: 30 })]],
    [`GET ${base}/t1/usage`]: [200, { last_24h: 2, recent: [
      { at: "2026-11-20T10:00:00Z", method: "GET", route: "/api/v1/frameworks", scope: "compliance:read" },
      { at: "2026-11-20T09:00:00Z", method: "GET", route: "/api/v1/key", scope: null },
    ] }],
  });
  renderWithProviders(<IntegrationsView org={owner} />);
  expect(await screen.findByText("Solo lectura")).toBeTruthy();
  expect(screen.getByText(/Leer el cumplimiento · Leer los incidentes · 30 por minuto/)).toBeTruthy();
  expect(requests.some((r) => r.url.endsWith("/usage"))).toBe(false);
  fireEvent.click(screen.getByText("Ver el uso de GitHub Actions"));
  expect(await screen.findByText("2 peticiones en las últimas 24 horas")).toBeTruthy();
  expect(screen.getByText("GET /api/v1/frameworks")).toBeTruthy();
  const log = screen.getByText("GET /api/v1/frameworks").closest("ol")!;
  const [first, second] = within(log).getAllByRole("listitem").map((item) => item.textContent ?? "");
  expect(first).toContain("Leer el cumplimiento");
  expect(second).toMatch(/GET \/api\/v1\/key · Ninguno$/);
});

it("names permissions in English", async () => {
  stubApi({ [`GET ${base}`]: [200, [row({ scopes: ["evidence:write", "assessment:propose"] })]] });
  renderWithProviders(<IntegrationsView org={owner} />, "en");
  expect(await screen.findByText(/Record evidence · Propose self-assessments · 60 per minute/)).toBeTruthy();
});
