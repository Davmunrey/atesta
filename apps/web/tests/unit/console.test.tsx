// @vitest-environment jsdom
import { act, cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AppLayout from "@/app/(app)/app/layout";
import { overview } from "../fixtures/overview";
import { renderWithProviders, stubApi } from "./render";

vi.mock("next/navigation", () => ({
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
  useRouter: () => ({ push: (url: string) => window.history.pushState(null, "", url) }),
}));

const me = {
  id: "u", email: "console@example.test", email_verified: true, locale: "es",
  memberships: [{ organization_id: "primary", organization_name: "Synthetic Team", role: "owner", access_expires_on: null, closure_erase_after: null }],
};
const measure = { framework_key: "synthetic_alpha", framework_name: "Synthetic Alpha", code: "op.acc.5", title_es: "Mecanismo de autenticación", title_en: null };

beforeEach(() => { localStorage.clear(); window.history.replaceState(null, "", "/app/org?org=primary"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function render() {
  stubApi({
    "GET /api/v1/me": [200, me],
    "GET /api/v1/orgs/primary/overview": [200, overview],
    "GET /api/v1/orgs/primary/search": [200, [measure]],
  });
  return renderWithProviders(<AppLayout><h1>Page</h1></AppLayout>);
}

it("groups the navigation with drawn icons and marks the current page", async () => {
  render();
  const nav = await screen.findByRole("navigation", { name: "Secciones de la organización" });
  expect(within(nav).getAllByRole("link").map((l) => l.textContent)).toEqual(["Resumen", "Mi trabajo", "Marcos", "Miembros", "Invitaciones", "Actividad", "Ajustes"]);
  expect(within(nav).getByRole("link", { name: "Resumen" }).getAttribute("aria-current")).toBe("page");
  expect(nav.querySelectorAll("svg[aria-hidden='true']")).toHaveLength(7);
});

it("collapses the navigation to icons and remembers it", async () => {
  render();
  const button = await screen.findByRole("button", { name: "Ocultar el menú" });
  expect(button.getAttribute("aria-expanded")).toBe("true");
  fireEvent.click(button);
  expect(localStorage.getItem("atesta_nav")).toBe("collapsed");
  expect(screen.getByRole("button", { name: "Mostrar el menú" }).getAttribute("aria-expanded")).toBe("false");
  // Labels stay as accessible names when only icons show.
  expect(within(screen.getByRole("navigation", { name: "Secciones de la organización" })).getByRole("link", { name: "Marcos" })).toBeTruthy();
});

it("searches pages, frameworks and measures, and opens a measure with the keyboard", async () => {
  render();
  const box = await screen.findByRole("combobox", { name: "Buscar en Atesta" });
  fireEvent.keyDown(document, { key: "k", ctrlKey: true });
  expect(document.activeElement).toBe(box);
  fireEvent.change(box, { target: { value: "auten" } });
  const list = await screen.findByRole("listbox", { name: "Buscar en Atesta" });
  await within(list).findByText("Mecanismo de autenticación");
  expect(box.getAttribute("aria-expanded")).toBe("true");
  fireEvent.keyDown(box, { key: "Enter" });
  expect(window.location.pathname + window.location.search + window.location.hash).toBe("/app/framework?org=primary&framework=synthetic_alpha#req-op.acc.5");
});

it("finds pages and frameworks by name before measures", async () => {
  render();
  const box = await screen.findByRole("combobox", { name: "Buscar en Atesta" });
  fireEvent.focus(box);
  fireEvent.change(box, { target: { value: "synthetic" } });
  const list = await screen.findByRole("listbox", { name: "Buscar en Atesta" });
  const options = await within(list).findAllByRole("option");
  expect(options[0]!.textContent).toContain("Marco");
  await act(async () => { fireEvent.keyDown(box, { key: "Escape" }); });
  expect((box as HTMLInputElement).value).toBe("");
});
