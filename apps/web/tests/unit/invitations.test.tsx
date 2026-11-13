// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuthGate } from "@/components/auth-gate";
import { InvitationsView } from "@/components/invitations-view";
import type { Role } from "@/lib/permissions";
import { renderWithProviders, stubApi } from "./render";

vi.mock("@/lib/navigation", () => ({ goTo: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ORG = "11111111-1111-1111-1111-111111111111";
const PATH = `/api/v1/orgs/${ORG}/invitations`;
const PENDING = [{ id: "i-1", email: "dan@example.com", role: "member", expires_at: "2026-11-20T10:00:00Z" }];
const membership = (role: Role) => ({ organization_id: ORG, organization_name: "Acme", role });

function show(role: Role, routes: Parameters<typeof stubApi>[0] = {}) {
  const me = { id: "u", email: "ana@example.com", email_verified: true, locale: "es", memberships: [membership(role)] };
  const requests = stubApi({ "GET /api/v1/me": [200, me], [`GET ${PATH}`]: [200, PENDING], ...routes });
  renderWithProviders(
    <AuthGate>
      <InvitationsView org={membership(role)} />
    </AuthGate>,
  );
  return requests;
}

it("creates an invitation and shows the link once, with a copy button", async () => {
  const link = "http://localhost:3000/invite#token=secret-token-value-123";
  const writeText = vi.fn(async () => {});
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  const requests = show("admin", {
    [`POST ${PATH}`]: [201, { id: "i-2", email: "eva@example.com", role: "admin", expires_at: "2026-11-20T10:00:00Z", accept_link: link }],
  });
  fireEvent.change(await screen.findByLabelText("Correo electrónico"), { target: { value: "eva@example.com" } });
  fireEvent.change(screen.getByLabelText("Rol"), { target: { value: "admin" } });
  fireEvent.click(screen.getByRole("button", { name: "Invitar" }));
  const shown = await screen.findByDisplayValue(link);
  expect(await requests.find((r) => r.method === "POST")!.json()).toEqual({ email: "eva@example.com", role: "admin" });
  expect(screen.getByText(/solo se muestra una vez/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Copiar enlace" }));
  expect(writeText).toHaveBeenCalledWith(link);
  expect(shown).toBeTruthy();
});

it("offers only roles up to the caller's own", async () => {
  show("admin");
  const options = within(await screen.findByLabelText("Rol")).getAllByRole("option");
  expect(options.map((o) => (o as HTMLOptionElement).value)).toEqual(["admin", "member"]);
});

it("lists pending invitations and revokes after confirmation", async () => {
  const requests = show("owner", { [`DELETE ${PATH}/i-1`]: [204, null] });
  const row = within((await screen.findByText("dan@example.com")).closest("li")!);
  fireEvent.click(row.getByRole("button", { name: "Revocar" }));
  expect(requests.some((r) => r.method === "DELETE")).toBe(false);
  fireEvent.click(row.getByRole("button", { name: "Confirmar" }));
  await vi.waitFor(() => expect(requests.some((r) => r.method === "DELETE")).toBe(true));
});
