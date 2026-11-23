// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AppLayout from "@/app/(app)/app/layout";
import { renderWithProviders, stubApi } from "./render";

vi.mock("next/navigation", () => ({
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ push: (url: string) => window.history.pushState(null, "", url) }),
}));

const primary = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const };
const secondary = { organization_id: "secondary", organization_name: "Other Synthetic Team", role: "member" as const };

function renderShell(role: "owner" | "admin" | "member" | "auditor" = "owner") {
  stubApi({ "GET /api/v1/me": [200, {
    id: "synthetic-user", email: "navigation@example.test", email_verified: true, locale: "es",
    memberships: [{ ...primary, role, access_expires_on: role === "auditor" ? "2026-12-31" : null }, secondary],
  }] });
  return renderWithProviders(<AppLayout><h1>Page content</h1></AppLayout>);
}

beforeEach(() => window.history.replaceState(null, "", "/app/members?org=primary"));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it.each(["owner", "admin"] as const)("keeps all organization sections reachable for %s", async (role) => {
  renderShell(role);
  const nav = await screen.findByRole("navigation", { name: "Secciones de la organización" });
  expect(within(nav).getByRole("link", { name: "Resumen" }).getAttribute("href")).toBe("/app/org?org=primary");
  expect(within(nav).getByRole("link", { name: "Miembros" }).getAttribute("aria-current")).toBe("page");
  expect(within(nav).getByRole("link", { name: "Invitaciones" }).getAttribute("href")).toBe("/app/invitations?org=primary");
  expect(within(nav).getAllByRole("link").filter((link) => link.getAttribute("aria-current") === "page")).toHaveLength(1);
});

it("hides invitations from a member", async () => {
  renderShell("member");
  const nav = await screen.findByRole("navigation", { name: "Secciones de la organización" });
  expect(within(nav).queryByRole("link", { name: "Invitaciones" })).toBeNull();
  expect(within(nav).getByRole("link", { name: "Miembros" })).toBeTruthy();
});

it("gives contributors Mi trabajo", async () => {
  renderShell("member");
  const nav = await screen.findByRole("navigation", { name: "Secciones de la organización" });
  expect(within(nav).getByRole("link", { name: "Mi trabajo" }).getAttribute("href")).toBe("/app/my-work?org=primary");
});

it("shows an auditor only what they may read, with the end of their access", async () => {
  window.history.replaceState(null, "", "/app/org?org=primary");
  renderShell("auditor");
  const nav = await screen.findByRole("navigation", { name: "Secciones de la organización" });
  expect(within(nav).getAllByRole("link").map((link) => link.textContent)).toEqual(["Resumen"]);
  expect(screen.getByRole("note").textContent).toBe("Acceso de auditor, solo lectura, hasta el 31 de diciembre de 2026");
});

it("gives owners the settings and warns every member of a closing organization", async () => {
  window.history.replaceState(null, "", "/app/org?org=primary");
  stubApi({ "GET /api/v1/me": [200, {
    id: "synthetic-user", email: "navigation@example.test", email_verified: true, locale: "es",
    memberships: [{ ...primary, closure_erase_after: "2026-12-23T10:00:00Z" }, secondary],
  }] });
  renderWithProviders(<AppLayout><h1>Page content</h1></AppLayout>);
  const nav = await screen.findByRole("navigation", { name: "Secciones de la organización" });
  expect(within(nav).getByRole("link", { name: "Ajustes" }).getAttribute("href")).toBe("/app/settings?org=primary");
  expect(screen.getByRole("note").textContent).toContain("se borrarán el 23 de diciembre de 2026");
});

it("keeps the members section when switching organizations", async () => {
  renderShell();
  fireEvent.change(await screen.findByLabelText("Organización"), { target: { value: "secondary" } });
  expect(window.location.pathname + window.location.search).toBe("/app/members?org=secondary");
});

it("returns to overview when the new organization does not permit invitations", async () => {
  window.history.replaceState(null, "", "/app/invitations?org=primary");
  renderShell();
  fireEvent.change(await screen.findByLabelText("Organización"), { target: { value: "secondary" } });
  expect(window.location.pathname + window.location.search).toBe("/app/org?org=secondary");
});

it.each(["/app", "/app/new", "/app/members?org=unknown"])("shows no organization navigation at %s", async (url) => {
  window.history.replaceState(null, "", url);
  renderShell();
  await screen.findByText(/navigation@example.test/);
  expect(screen.queryByRole("navigation", { name: "Secciones de la organización" })).toBeNull();
  expect(screen.queryByLabelText("Organización")).toBeNull();
});

it("provides a skip link to the main content", async () => {
  renderShell();
  await screen.findByText(/navigation@example.test/);
  expect(screen.getByRole("link", { name: "Saltar al contenido" }).getAttribute("href")).toBe("#main-content");
  expect(screen.getByRole("main").id).toBe("main-content");
});
