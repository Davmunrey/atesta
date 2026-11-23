// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
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
    "El ENS no cabe en una hoja de cálculo", "Cómo funciona", "Un año de ENS",
    "ENS primero, y más según tu plan", "Tu próxima auditoría, preparada.",
  ]);
  const steps = [...document.querySelectorAll(".landing-steps > li")] as HTMLElement[];
  expect(steps).toHaveLength(4);
  expect(within(steps[0]!.querySelector(".landing-step-title") as HTMLElement).getByText("Próximamente")).toBeTruthy();
  for (const step of steps.slice(1)) expect(within(step).queryByText("Próximamente")).toBeNull();
  expect(screen.getByRole("heading", { level: 1 }).querySelector("mark")!.textContent).toBe("ENS");
});

// Amendment A2 (issue 356): pinned steps, a year of ENS, a pausable marquee.
it("pins one product frame beside the steps, with a counter, hidden from assistive technology", () => {
  renderWithProviders(<Landing />);
  const pinned = document.querySelector(".landing-pinned")!;
  expect(pinned.getAttribute("data-stage")).toBe("1");
  const frame = pinned.querySelector(".landing-stage-frame")!;
  expect(frame.getAttribute("aria-hidden")).toBe("true");
  expect(frame.querySelectorAll("[data-stage-view]")).toHaveLength(4);
  expect(frame.querySelector(".landing-stage-counter")!.textContent).toBe("01 / 04");
});

it("walks a year of ENS in six dated steps of sample data", () => {
  renderWithProviders(<Landing />);
  const year = screen.getByRole("heading", { level: 2, name: "Un año de ENS" }).closest("section")!;
  expect(within(year).getAllByRole("listitem")).toHaveLength(6);
  expect(within(year).getByText("Datos de ejemplo")).toBeTruthy();
});

it("lets the frameworks strip be paused with a visible button", () => {
  renderWithProviders(<Landing />);
  const button = screen.getByRole("button", { name: "Pausar la animación" });
  expect(button.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(button);
  expect(button.getAttribute("aria-pressed")).toBe("true");
  expect(button.closest(".landing-marquee")!.getAttribute("data-paused")).toBe("true");
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

it("stages the product moments the console ships inside the pinned steps", () => {
  renderWithProviders(<Landing />);
  const stages = [...document.querySelectorAll(".landing-stage-frame [data-stage-view]")].map((el) => el.getAttribute("data-stage-view"));
  expect(stages).toEqual(["connect", "assess", "routines", "dossier"]);
  expect(screen.getAllByText(fixture.measure.excerpt_es)[0]!.closest("[lang]")!.getAttribute("lang")).toBe("es");
  expect(screen.getAllByRole("figure").length).toBeGreaterThanOrEqual(4);
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
