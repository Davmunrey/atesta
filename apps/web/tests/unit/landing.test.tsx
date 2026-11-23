// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Landing from "@/app/(public)/page";
import { PublicHeader } from "@/components/public-header";
import { legalEntity } from "@/content/legal-entity";
import fixture from "@/content/landing-fixture.json";
import en from "../../messages/en.json";
import es from "../../messages/es.json";
import { legalIssues } from "../../scripts/check-legal";
import { renderWithProviders } from "./render";

// Landing, part 1 (landing-legal spec, L6, issue 308).
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
afterEach(cleanup);

function words(value: unknown): number {
  if (typeof value === "string") return value.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;
  if (value && typeof value === "object") return Object.entries(value).filter(([key]) => key !== "view").reduce((n, [, v]) => n + words(v), 0);
  return 0;
}

// Amendment A1 (accepted by the owner, 2026-11-23): up to 200 words of marketing copy.
it.each([["es", es], ["en", en]])("keeps the %s marketing copy within 200 words, product views excluded", (_, messages) => {
  expect(words(messages.landing)).toBeLessThanOrEqual(200);
  expect(words(messages.landing)).toBeGreaterThan(120);
});

it("runs the amended sections in order, with the scan step marked as coming soon", () => {
  renderWithProviders(<Landing />);
  expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
    "El ENS no cabe en una hoja de cálculo", "Cómo funciona",
    "El texto oficial de cada medida", "Los registros que pide el auditor", "Un dossier listo para firmar",
    "ENS primero, y más según tu plan", "Tu próxima auditoría, preparada.",
  ]);
  const steps = screen.getAllByRole("listitem").filter((li) => li.closest(".landing-steps"));
  expect(steps).toHaveLength(4);
  expect(within(steps[0]!).getByText("Próximamente")).toBeTruthy();
  for (const step of steps.slice(1)) expect(within(step).queryByText("Próximamente")).toBeNull();
  expect(screen.getByRole("heading", { level: 1 }).querySelector("mark")!.textContent).toBe("ENS");
});

it("labels every product view as sample data", () => {
  renderWithProviders(<Landing />);
  for (const figure of screen.getAllByRole("figure")) expect(within(figure).getByText("Datos de ejemplo")).toBeTruthy();
});

it("names every ENS measure in the product view exactly as the catalog does", () => {
  const yaml = readFileSync(join(import.meta.dirname, "../../../../catalog/frameworks/ens_rd311_2022/requirements.yaml"), "utf8");
  const catalog = new Map([...yaml.matchAll(/^- id: (\S+)\n {2}title_es: (.+)$/gm)].map((m) => [m[1]!, m[2]!]));
  expect(fixture.origin).toBe("illustrative");
  expect(fixture.attention.length).toBeGreaterThan(0);
  for (const item of fixture.attention) expect(catalog.get(item.code), item.code).toBe(item.title_es);
  expect(fixture.counts.total).toBe(catalog.size);
});

it("quotes the measure's official text exactly as the catalog holds it", () => {
  const yaml = readFileSync(join(import.meta.dirname, "../../../../catalog/frameworks/ens_rd311_2022/requirements.yaml"), "utf8");
  const start = yaml.indexOf(`- id: ${fixture.measure.code}\n`);
  const block = yaml.slice(start, yaml.indexOf("\n- id: ", start + 5));
  expect(block).toContain(`title_es: ${fixture.measure.title_es}`);
  expect(block).toContain(fixture.measure.excerpt_es);
});

it("shows three product moments the console ships, each under a short headline", () => {
  renderWithProviders(<Landing />);
  const moments = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
  expect(moments.slice(2, 5)).toEqual(["El texto oficial de cada medida", "Los registros que pide el auditor", "Un dossier listo para firmar"]);
  for (const title of moments.slice(2, 5)) expect(title!.split(" ").length).toBeLessThanOrEqual(6);
  expect(screen.getByText(fixture.measure.excerpt_es).closest("[lang]")!.getAttribute("lang")).toBe("es");
  expect(screen.getAllByRole("figure")).toHaveLength(4);
});

it("leads with the ENS, says what else it covers, and asks for access by email", () => {
  renderWithProviders(<Landing />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Prepara el ENS sin un consultor a tiempo completo");
  expect(screen.getByText("También cubre NIS2, RGPD, LOPDGDD y DORA. Una misma evidencia sirve a varios marcos.")).toBeTruthy();
  const requests = screen.getAllByRole("link", { name: "Solicitar acceso" });
  expect(requests.length).toBeGreaterThan(0);
  for (const link of requests) expect(link.getAttribute("href")).toBe(`mailto:${legalEntity.email}`);
  const view = screen.getAllByRole("figure")[0]!;
  expect(within(view).getByText("op.acc.6")).toBeTruthy();
});

it("puts the brand lockup, sign-in and the access request in the landing header", () => {
  renderWithProviders(<PublicHeader />);
  const home = screen.getByRole("link", { name: "Volver al inicio de Atesta" });
  expect(home.querySelector("svg[aria-hidden='true']")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Entrar" }).getAttribute("href")).toBe("/auth/login?lang=es");
  expect(screen.getByRole("link", { name: "Solicitar acceso" }).getAttribute("href")).toBe(`mailto:${legalEntity.email}`);
});

it("blocks a release while any legal field is still a placeholder", () => {
  expect(legalIssues(legalEntity)).toEqual(["name", "nif", "address", "registry"]);
  expect(legalEntity.email).toBe("hello@atesta.cloud");
  expect(legalIssues({ name: "A", nif: "B", address: "C", registry: "D", email: "pendiente@atesta.invalid" })).toEqual(["email"]);
});
