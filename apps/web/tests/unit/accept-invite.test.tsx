// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AcceptInvite } from "@/components/accept-invite";
import { INVITE_KEY } from "@/lib/invite";
import { goTo } from "@/lib/navigation";
import { renderWithProviders, stubApi } from "./render";

vi.mock("@/lib/navigation", () => ({ goTo: vi.fn() }));
const ME = { id: "u", email: "eva@example.com", email_verified: true, locale: "es", memberships: [] };
const TOKEN = "secret-token-value-1234567890";

beforeEach(() => {
  sessionStorage.clear();
  window.history.replaceState(null, "", `/invite#token=${TOKEN}`);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(goTo).mockReset();
});

it("a signed-out visitor keeps the token and signs in, coming back to /invite", async () => {
  stubApi({ "GET /api/v1/me": [401, { detail: { code: "auth.invalid_token" } }] });
  renderWithProviders(<AcceptInvite />);
  await vi.waitFor(() => expect(goTo).toHaveBeenCalledWith("/auth/login?lang=es&return_to=%2Finvite"));
  expect(sessionStorage.getItem(INVITE_KEY)).toBe(TOKEN);
  expect(window.location.hash).toBe("");
});

it("accepting posts the token in the body, then forgets it and opens the org", async () => {
  const requests = stubApi({
    "GET /api/v1/me": [200, ME],
    "POST /api/v1/invitations/accept": [200, { organization_id: "org-9", role: "member" }],
  });
  renderWithProviders(<AcceptInvite />);
  fireEvent.click(await screen.findByRole("button", { name: "Aceptar invitación" }));
  await vi.waitFor(() => expect(goTo).toHaveBeenCalledWith("/app/org?org=org-9"));
  const post = requests.find((r) => r.method === "POST")!;
  expect(new URL(post.url).search).toBe("");
  expect(await post.json()).toEqual({ token: TOKEN });
  expect(sessionStorage.getItem(INVITE_KEY)).toBeNull();
});

it("a wrong account keeps the token so another sign-in can use it", async () => {
  stubApi({
    "GET /api/v1/me": [200, ME],
    "POST /api/v1/invitations/accept": [403, { detail: { code: "identity.email_mismatch" } }],
  });
  renderWithProviders(<AcceptInvite />);
  fireEvent.click(await screen.findByRole("button", { name: "Aceptar invitación" }));
  expect((await screen.findByRole("alert")).textContent).toMatch(/otro correo/);
  expect(sessionStorage.getItem(INVITE_KEY)).toBe(TOKEN);
});

it("a dead invitation is forgotten", async () => {
  stubApi({
    "GET /api/v1/me": [200, ME],
    "POST /api/v1/invitations/accept": [410, { detail: { code: "identity.invitation_invalid" } }],
  });
  renderWithProviders(<AcceptInvite />);
  fireEvent.click(await screen.findByRole("button", { name: "Aceptar invitación" }));
  await screen.findByRole("alert");
  expect(sessionStorage.getItem(INVITE_KEY)).toBeNull();
});

it("without a token it says so", async () => {
  window.history.replaceState(null, "", "/invite");
  stubApi({ "GET /api/v1/me": [200, ME] });
  renderWithProviders(<AcceptInvite />);
  expect((await screen.findByRole("alert")).textContent).toMatch(/no es válido/);
});
