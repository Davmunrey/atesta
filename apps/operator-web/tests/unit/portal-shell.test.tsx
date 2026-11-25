// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PortalShell, useStaff } from "@/components/portal-shell";
import { renderWithProviders, stubApi } from "./render";

let pathname = "/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

function Email() {
  return <p data-testid="page">{useStaff().email}</p>;
}

beforeEach(() => { pathname = "/"; window.history.replaceState(null, "", "/organization?id=o-1"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const me = (role: string) => ({ "GET /api/v1/me": [200, { email: `${role}@atesta.test`, role }] as [number, unknown] });

it("names itself the operations portal, in both languages", async () => {
  stubApi(me("support"));
  renderWithProviders(<PortalShell><Email /></PortalShell>);
  expect((await screen.findByTestId("page")).textContent).toBe("support@atesta.test");
  const bar = screen.getByRole("banner");
  expect(within(bar).getByText("Portal de operaciones")).toBeTruthy();
  expect(within(bar).getByRole("link", { name: "Atesta · Portal de operaciones" }).getAttribute("href")).toBe("/");
  cleanup();
  renderWithProviders(<PortalShell><Email /></PortalShell>, "en");
  expect(await screen.findByText("Operations portal")).toBeTruthy();
});

it("shows an admin every section and support only the organizations", async () => {
  stubApi(me("admin"));
  renderWithProviders(<PortalShell><Email /></PortalShell>);
  const nav = await screen.findByRole("navigation", { name: "Secciones del portal" });
  expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(
    ["Organizaciones", "Organizaciones borradas", "Equipo", "Registro de operaciones"]);
  expect(within(nav).getByRole("link", { name: "Organizaciones" }).getAttribute("aria-current")).toBe("page");
  cleanup();
  for (const role of ["billing", "support"]) {
    stubApi(me(role));
    renderWithProviders(<PortalShell><Email /></PortalShell>);
    const limited = await screen.findByRole("navigation", { name: "Secciones del portal" });
    expect(within(limited).getAllByRole("link").map((a) => a.textContent), role).toEqual(["Organizaciones"]);
    cleanup();
  }
});

it("lights up Organizaciones on an organization's page and names the role in the account menu", async () => {
  pathname = "/organization";
  stubApi(me("billing"));
  renderWithProviders(<PortalShell><Email /></PortalShell>);
  const nav = await screen.findByRole("navigation", { name: "Secciones del portal" });
  expect(within(nav).getByRole("link", { name: "Organizaciones" }).getAttribute("aria-current")).toBe("page");
  expect(screen.getByText("Facturación")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Cerrar sesión", hidden: true }).getAttribute("href")).toBe("/auth/logout");
});

it("signed out, offers the staff sign-in and comes back to the same page", async () => {
  stubApi({ "GET /api/v1/me": [401, { detail: { code: "auth.invalid_token" } }] });
  renderWithProviders(<PortalShell><Email /></PortalShell>);
  const link = await screen.findByRole("link", { name: "Iniciar sesión" });
  expect(link.getAttribute("href")).toBe("/auth/login?lang=es&return_to=%2Forganization%3Fid%3Do-1");
  expect(screen.queryByRole("navigation", { name: "Secciones del portal" })).toBeNull();
  expect(screen.queryByTestId("page")).toBeNull();
});

it("a staff account without access reads why and can sign out", async () => {
  stubApi({ "GET /api/v1/me": [403, { detail: { code: "operator.forbidden" } }] });
  renderWithProviders(<PortalShell><Email /></PortalShell>);
  expect(await screen.findByRole("heading", { name: "Sin acceso al portal" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Cerrar sesión" }).getAttribute("href")).toBe("/auth/logout");
  expect(screen.queryByRole("navigation", { name: "Secciones del portal" })).toBeNull();
});

it("another failure shows its message and a retry, never the raw code", async () => {
  stubApi({ "GET /api/v1/me": [500, { detail: { code: "server.error" } }] });
  renderWithProviders(<PortalShell><Email /></PortalShell>);
  expect((await screen.findByRole("alert")).textContent).toContain("Algo ha fallado por nuestra parte");
  expect(screen.getByRole("button", { name: "Reintentar" })).toBeTruthy();
});
