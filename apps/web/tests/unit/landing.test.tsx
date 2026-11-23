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

it.each([["es", es], ["en", en]])("keeps the %s marketing copy within 60 words, product views excluded", (_, messages) => {
  expect(words(messages.landing)).toBeLessThanOrEqual(60);
  expect(words(messages.landing)).toBeGreaterThan(20);
});

it("names every ENS measure in the product view exactly as the catalog does", () => {
  const yaml = readFileSync(join(import.meta.dirname, "../../../../catalog/frameworks/ens_rd311_2022/requirements.yaml"), "utf8");
  const catalog = new Map([...yaml.matchAll(/^- id: (\S+)\n {2}title_es: (.+)$/gm)].map((m) => [m[1]!, m[2]!]));
  expect(fixture.origin).toBe("illustrative");
  expect(fixture.attention.length).toBeGreaterThan(0);
  for (const item of fixture.attention) expect(catalog.get(item.code), item.code).toBe(item.title_es);
  expect(fixture.counts.total).toBe(catalog.size);
});

it("leads with the ENS, says what else it covers, and asks for access by email", () => {
  renderWithProviders(<Landing />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Prepara el ENS sin un consultor a tiempo completo");
  expect(screen.getByText("También cubre, según el plan: NIS2, RGPD, LOPDGDD y DORA.")).toBeTruthy();
  const requests = screen.getAllByRole("link", { name: "Solicitar acceso" });
  expect(requests.length).toBeGreaterThan(0);
  for (const link of requests) expect(link.getAttribute("href")).toBe(`mailto:${legalEntity.email}`);
  const view = screen.getByRole("figure");
  expect(within(view).getByText("op.acc.6")).toBeTruthy();
});

it("puts sign-in and the access request in the landing header", () => {
  renderWithProviders(<PublicHeader />);
  expect(screen.getByRole("link", { name: "Entrar" }).getAttribute("href")).toBe("/auth/login?lang=es");
  expect(screen.getByRole("link", { name: "Solicitar acceso" }).getAttribute("href")).toBe(`mailto:${legalEntity.email}`);
});

it("blocks a release while any legal field is still a placeholder", () => {
  expect(legalIssues(legalEntity)).toEqual(["name", "nif", "address", "registry", "email"]);
  expect(legalIssues({ name: "A", nif: "B", address: "C", registry: "D", email: "pendiente@atesta.invalid" })).toEqual(["email"]);
});
