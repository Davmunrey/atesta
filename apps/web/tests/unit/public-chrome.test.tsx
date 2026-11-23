// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CustomerLogos } from "@/components/public/customer-logos";
import { ProofStrip } from "@/components/public/proof-strip";
import { PublicFooter } from "@/components/public/public-footer";
import { PAGES } from "@/components/public/site-map";
import { PublicHeader } from "@/components/public-header";
import { renderWithProviders } from "./render";

// Public chrome (landing-legal amendment A3, issue 371).
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
afterEach(cleanup);

it("opens the product and docs menus as disclosures, and closes them on Escape", () => {
  renderWithProviders(<PublicHeader />);
  const producto = screen.getByRole("button", { name: "Producto" });
  expect(producto.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(producto);
  expect(producto.getAttribute("aria-expanded")).toBe("true");
  const panel = document.getElementById(producto.getAttribute("aria-controls")!)!;
  expect(within(panel).getByRole("link", { name: /API y MCP/ }).getAttribute("href")).toBe("/producto#api");
  fireEvent.keyDown(document, { key: "Escape" });
  expect(producto.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(screen.getByRole("button", { name: "Docs" }));
  expect(screen.getByRole("link", { name: /MCP/ }).getAttribute("href")).toBe("/docs/mcp");
});

it("links only to public pages that exist", () => {
  renderWithProviders(<PublicHeader />);
  const pages = { "/producto": PAGES.producto, "/ens": PAGES.ens, "/seguridad": PAGES.seguridad, "/consultoras": PAGES.consultoras };
  const linked = (href: string) => [...document.querySelectorAll("a")].some((a) => a.getAttribute("href")?.split("#")[0] === href);
  for (const [href, live] of Object.entries(pages)) expect(linked(href), href).toBe(live);
});

it("maps the public site in the footer, with the honest proof and no person's name", () => {
  renderWithProviders(<PublicFooter />);
  const footer = screen.getByRole("contentinfo");
  for (const href of ["/aviso-legal", "/privacidad", "/cookies", "/docs/api", "/docs/mcp"]) expect(footer.querySelector(`a[href="${href}"]`)).toBeTruthy();
  expect(within(footer).getByText("No certifica cumplimiento.", { exact: false })).toBeTruthy();
  expect(footer.textContent).not.toMatch(/Muñoz/);
});

it("states five facts that are true today", () => {
  renderWithProviders(<ProofStrip />);
  const facts = screen.getAllByRole("listitem").map((li) => li.textContent);
  expect(facts).toHaveLength(5);
  expect(facts.join(" ")).toContain("revisadas por el equipo de Atesta");
  expect(facts.join(" ")).toContain("Diseñado para alojarse en España");
});

it("renders no customer section while there is no written permission", () => {
  const { container } = renderWithProviders(<CustomerLogos />);
  expect(container.innerHTML).toBe("");
});
