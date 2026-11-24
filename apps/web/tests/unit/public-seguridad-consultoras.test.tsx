// @vitest-environment jsdom
/** /seguridad and /consultoras (landing-legal amendment A3, issue 381). */
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Consultoras from "@/app/(public)/consultoras/page";
import Seguridad from "@/app/(public)/seguridad/page";
import { LINKS, PAGES } from "@/components/public/site-map";
import en from "../../messages/en.json";
import es from "../../messages/es.json";
import { renderWithProviders } from "./render";

vi.mock("next/navigation", () => ({ usePathname: () => "/seguridad" }));
afterEach(cleanup);

function words(value: unknown): number {
  if (typeof value === "string") return value.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;
  if (value && typeof value === "object") return Object.values(value).reduce((n: number, v) => n + words(v), 0);
  return 0;
}

/** What these pages must never claim (owner and coordinator, 2026-11-23 and 2026-11-24). */
const OVERCLAIMS = /certificad|certified|pentest|penetration|auditad[oa] por|audited by|partner|socio|nuestros clientes|our customers|confían|trusted by|\d+\s?%|99[.,]9/i;

it.each([["es", es], ["en", en]])("keeps the %s copy within the A3 budgets: /seguridad 400 words, /consultoras 250", (_, messages) => {
  expect(words(messages.seguridad)).toBeLessThanOrEqual(400);
  expect(words(messages.consultoras)).toBeLessThanOrEqual(250);
  expect(words(messages.seguridad)).toBeGreaterThan(150);
  expect(words(messages.consultoras)).toBeGreaterThan(60);
});

it.each([["es", es], ["en", en]])("makes no certification, pentest, figure, partner or customer claim in %s", (_, messages) => {
  expect(JSON.stringify(messages.seguridad)).not.toMatch(OVERCLAIMS);
  expect(JSON.stringify(messages.consultoras)).not.toMatch(OVERCLAIMS);
});

it("turns both pages on in the site map", () => {
  expect(PAGES.seguridad).toBe(true);
  expect(PAGES.consultoras).toBe(true);
  expect(LINKS.map((l) => l.href)).toEqual(expect.arrayContaining(["/seguridad", "/consultoras"]));
});

it("/seguridad says hosting is designed for eu-south-2, not live, and draws what Atesta can touch", () => {
  renderWithProviders(<Seguridad />);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  const main = screen.getByRole("main");
  expect(main.textContent).toContain("diseñada para desplegarse en AWS eu-south-2 (Aragón)");
  expect(main.textContent).not.toMatch(/Muñoz|Davmunrey/);
  const diagram = screen.getByRole("figure", { name: /qué puede tocar/i });
  for (const name of ["Microsoft 365", "Google Workspace"]) {
    const item = within(diagram).getByText(name).closest("li") as HTMLElement;
    expect(item.textContent).toContain("Próximamente");
  }
  expect(diagram.textContent).toMatch(/sin permisos de escritura/i);
});

it("/seguridad names both residency exceptions of ADR-007", () => {
  renderWithProviders(<Seguridad />);
  const text = screen.getByRole("main").textContent ?? "";
  expect(text).toContain("París");
  expect(text).toContain("CloudFront");
});

it("/consultoras shows a sample portfolio with the console's own column names and fictitious clients", () => {
  renderWithProviders(<Consultoras />);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  const view = screen.getByRole("figure");
  expect(view.textContent).toContain("Datos de ejemplo");
  const headers = within(view).getAllByRole("columnheader").map((th) => th.textContent);
  expect(headers).toEqual([es.portfolio.organization, es.portfolio.assessed, es.portfolio.overdue, es.portfolio.routines, es.portfolio.lastAssessed]);
  const names = within(view).getAllByRole("rowheader").map((th) => th.textContent);
  expect(names.length).toBeGreaterThanOrEqual(3);
  for (const name of names) expect(name).toMatch(/Ejemplo/);
});
