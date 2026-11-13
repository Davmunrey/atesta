// @vitest-environment jsdom
import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthGate, useMe } from "@/components/auth-gate";
import { goTo } from "@/lib/navigation";
import { renderWithProviders, stubFetch } from "./render";

vi.mock("@/lib/navigation", () => ({ goTo: vi.fn() }));

function Email() {
  return <p>{useMe().email}</p>;
}

beforeEach(() => window.history.replaceState(null, "", "/app/org?org=1"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(goTo).mockReset();
});

it("a signed-out visitor goes to sign-in and comes back to the same page", async () => {
  const requests = stubFetch([401, { detail: { code: "auth.invalid_token" } }]);
  renderWithProviders(<AuthGate><Email /></AuthGate>);
  await vi.waitFor(() => expect(goTo).toHaveBeenCalledWith("/auth/login?lang=es&return_to=%2Fapp%2Forg%3Forg%3D1"));
  expect(new URL(requests[0]!.url).pathname).toBe("/api/v1/me");
});

it("a signed-in user sees the page", async () => {
  stubFetch([200, { id: "u", email: "ana@example.com", email_verified: true, locale: "es", memberships: [] }]);
  renderWithProviders(<AuthGate><Email /></AuthGate>);
  expect(await screen.findByText("ana@example.com")).toBeTruthy();
  expect(goTo).not.toHaveBeenCalled();
});

it("other failures show a message, not the raw code", async () => {
  stubFetch([500, { detail: { code: "internal.boom" } }]);
  renderWithProviders(<AuthGate><Email /></AuthGate>);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).not.toContain("internal.boom");
  expect(goTo).not.toHaveBeenCalled();
});
