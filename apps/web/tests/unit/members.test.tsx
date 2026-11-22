// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuthGate } from "@/components/auth-gate";
import { MembersView } from "@/components/members-view";
import type { Role } from "@/lib/permissions";
import { renderWithProviders, stubApi } from "./render";

vi.mock("@/lib/navigation", () => ({ goTo: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ORG = "11111111-1111-1111-1111-111111111111";
const MEMBERS = [
  { user_id: "u-ana", email: "ana@example.com", display_name: "Ana", role: "owner" },
  { user_id: "u-bea", email: "bea@example.com", display_name: null, role: "admin" },
  { user_id: "u-cai", email: "cai@example.com", display_name: null, role: "member" },
];

function me(role: Role) {
  return {
    id: "u-ana", email: "ana@example.com", email_verified: true, locale: "es",
    memberships: [{ organization_id: ORG, organization_name: "Acme", role }],
  };
}

const PATH = `/api/v1/orgs/${ORG}/members`;

function show(role: Role, routes: Parameters<typeof stubApi>[0] = {}) {
  const requests = stubApi({ "GET /api/v1/me": [200, me(role)], [`GET ${PATH}`]: [200, MEMBERS], ...routes });
  renderWithProviders(
    <AuthGate>
      <MembersView org={me(role).memberships[0]!} />
    </AuthGate>,
  );
  return requests;
}

const row = async (email: string) => within((await screen.findByText(email)).closest("tr")!);

it("an owner changes a role", async () => {
  const requests = show("owner", { [`PATCH ${PATH}/u-cai`]: [200, { ...MEMBERS[2], role: "admin" }] });
  fireEvent.change((await row("cai@example.com")).getByRole("combobox"), { target: { value: "admin" } });
  await vi.waitFor(() => expect(requests.some((r) => r.method === "PATCH")).toBe(true));
  expect(await requests.find((r) => r.method === "PATCH")!.json()).toEqual({ role: "admin", access_expires_on: null });
});

it("removing asks for confirmation, then deletes", async () => {
  const requests = show("owner", { [`DELETE ${PATH}/u-cai`]: [204, null] });
  const cai = await row("cai@example.com");
  fireEvent.click(cai.getByRole("button", { name: "Quitar" }));
  expect(requests.some((r) => r.method === "DELETE")).toBe(false);
  fireEvent.click(cai.getByRole("button", { name: "Confirmar" }));
  await vi.waitFor(() => expect(requests.some((r) => r.method === "DELETE")).toBe(true));
});

it("an admin cannot change roles and removes only members", async () => {
  show("admin");
  expect((await row("cai@example.com")).queryByRole("button", { name: "Quitar" })).not.toBeNull();
  expect((await row("bea@example.com")).queryByRole("button", { name: "Quitar" })).toBeNull();
  expect(screen.queryAllByRole("combobox")).toHaveLength(0);
});

it("a member only reads the list", async () => {
  show("member");
  await screen.findByText("cai@example.com");
  expect(screen.queryAllByRole("button", { name: "Quitar" })).toHaveLength(0);
  expect(screen.queryAllByRole("combobox")).toHaveLength(0);
});

it("the API's refusal is shown in Spanish", async () => {
  show("owner", { [`DELETE ${PATH}/u-ana`]: [409, { detail: { code: "identity.last_owner" } }] });
  const ana = await row("ana@example.com");
  fireEvent.click(ana.getByRole("button", { name: "Quitar" }));
  fireEvent.click(ana.getByRole("button", { name: "Confirmar" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/al menos un propietario/);
});
