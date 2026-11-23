// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import LegalNotice from "@/app/(public)/aviso-legal/page";
import Privacy from "@/app/(public)/privacidad/page";
import { SiteFooter } from "@/components/site-footer";
import { legalEntity } from "@/content/legal-entity";
import { renderWithProviders } from "./render";

// Draft legal pages (landing-legal spec, issue 316): structure per LSSI art. 10 and RGPD art. 13,
// every clause marked as a draft, identity only from legal-entity.ts.
afterEach(cleanup);

it("drafts the aviso legal with one section per LSSI item and the owner's placeholders", () => {
  renderWithProviders(<LegalNotice />);
  expect(screen.getByRole("heading", { level: 1, name: "Aviso legal" })).toBeTruthy();
  expect(screen.getByRole("note").textContent).toContain("Borrador pendiente de revisión jurídica");
  const sections = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
  expect(sections).toEqual(["Titular del sitio", "Inscripción registral", "Número de identificación fiscal", "Códigos de conducta", "Precios"]);
  for (const value of [legalEntity.name, legalEntity.address, legalEntity.nif, legalEntity.registry, legalEntity.email]) expect(screen.getByText(value)).toBeTruthy();
  for (const section of document.querySelectorAll("main section")) expect(within(section as HTMLElement).getByText("Borrador")).toBeTruthy();
});

it("drafts the privacy policy with one section per RGPD article 13 item", () => {
  renderWithProviders(<Privacy />);
  expect(screen.getByRole("heading", { level: 1, name: "Política de privacidad" })).toBeTruthy();
  expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(12);
  expect(screen.getByText(/eu-south-2/)).toBeTruthy();
  for (const section of document.querySelectorAll("main section")) expect(within(section as HTMLElement).getByText("Borrador")).toBeTruthy();
});

it("says in English that the Spanish text binds", () => {
  renderWithProviders(<LegalNotice />, "en");
  expect(screen.getByText("The Spanish version of this page is the binding one.")).toBeTruthy();
});

it("links both legal pages from the footer", () => {
  renderWithProviders(<SiteFooter />);
  expect(screen.getByRole("link", { name: "Aviso legal" }).getAttribute("href")).toBe("/aviso-legal");
  expect(screen.getByRole("link", { name: "Privacidad" }).getAttribute("href")).toBe("/privacidad");
});
