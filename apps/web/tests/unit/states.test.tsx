// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AuthGate } from "@/components/auth-gate";
import { MembersView } from "@/components/members-view";
import { PoliciesView } from "@/components/policies-view";
import { ApiError } from "@atesta/ui/api-error";
import { retryQuery } from "@atesta/ui/api-error";
import { renderWithProviders, stubApi } from "./render";

// Loading, error and empty states (ui-polish spec, #283).
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };

it("offers a retry when a list fails to load, and the retry refetches", async () => {
  const requests = stubApi({ "GET /api/v1/orgs/primary/policies": [[500, { error: { code: "internal" } }], [200, []]] });
  renderWithProviders(<PoliciesView org={owner} />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findByText("Aún no hay políticas registradas.")).toBeTruthy();
  expect(requests.filter((r) => r.url.endsWith("/policies"))).toHaveLength(2);
});

it("keeps the page header while a page loads, with visible status text", async () => {
  vi.stubGlobal("fetch", vi.fn(async (request: Request) => new URL(request.url).pathname === "/api/v1/me"
    ? new Response(JSON.stringify({ id: "u", email: "a@example.com", email_verified: true, locale: "es", memberships: [owner] }), { status: 200, headers: { "content-type": "application/json" } })
    : new Promise<Response>(() => {})));
  renderWithProviders(<AuthGate><MembersView org={owner} /></AuthGate>);
  expect(await screen.findByRole("heading", { level: 1, name: "Miembros de Synthetic Team" })).toBeTruthy();
  expect(screen.getByRole("status").textContent).toBe("Cargando…");
});

it("never retries a 4xx answer and retries a server or network failure once", () => {
  expect(retryQuery(0, new ApiError(404, "identity.not_found"))).toBe(false);
  expect(retryQuery(0, new ApiError(403, null))).toBe(false);
  expect(retryQuery(0, new ApiError(500, null))).toBe(true);
  expect(retryQuery(0, new TypeError("Failed to fetch"))).toBe(true);
  expect(retryQuery(1, new ApiError(503, null))).toBe(false);
});
