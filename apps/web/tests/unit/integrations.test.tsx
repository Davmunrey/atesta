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
  id: "t1", name: "GitHub Actions", prefix: "atesta_kkkkk", scope: "evidence:write", created_by_email: "ana@example.com",
  created_at: "2026-11-01T10:00:00Z", expires_at: "2099-01-30T10:00:00Z", last_used_at: null, revoked_at: null, ...over,
});

it("shows a new token once, with a curl example, and never lists it again", async () => {
  const requests = stubApi({
    [`GET ${base}`]: [[200, []], [200, [row({})]]],
    [`POST ${base}`]: [201, { ...row({}), token: TOKEN }],
  });
  renderWithProviders(<IntegrationsView org={owner} />);
  fireEvent.change(await screen.findByLabelText("Nombre"), { target: { value: "GitHub Actions" } });
  fireEvent.click(screen.getByRole("button", { name: "Crear el token" }));
  expect(await screen.findByDisplayValue(TOKEN)).toBeTruthy();
  expect((screen.getByLabelText("Ejemplo de uso") as HTMLTextAreaElement).value).toContain(`Authorization: Bearer ${TOKEN}`);
  const post = requests.find((r) => r.method === "POST")!;
  expect(await post.clone().json()).toEqual({ name: "GitHub Actions", expires_in_days: 90 });
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
  // Once in the token's row and once as the summary's last use (ui-polish spec).
  expect(screen.getAllByText("Never")).toHaveLength(2);
});
