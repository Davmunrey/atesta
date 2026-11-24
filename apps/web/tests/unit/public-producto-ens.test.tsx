// @vitest-environment jsdom
/** /producto and /ens (landing-legal amendment A3, issue 377). */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { load } from "js-yaml";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { buildIndex } from "../../scripts/assistant-index";
import Producto from "@/app/(public)/producto/page";
import { EnsPage } from "@/components/public/ens-page";
import { LINKS, PAGES, PRODUCT } from "@/components/public/site-map";
import { MCP_TOOLS } from "@/components/mcp-guide";
import fixture from "@/content/landing-fixture.json";
import faq from "@/content/assistant-faq.json";
import { loadEnsCatalog } from "@/lib/catalog/ens";
import en from "../../messages/en.json";
import es from "../../messages/es.json";
import { renderWithProviders } from "./render";

vi.mock("next/navigation", () => ({ usePathname: () => "/producto" }));
const CATALOG = join(import.meta.dirname, "../../../../catalog");
const index = buildIndex(CATALOG, faq);
beforeEach(() => { vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(index), { headers: { "content-type": "application/json" } }))); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function words(value: unknown): number {
  if (typeof value === "string") return value.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;
  if (value && typeof value === "object") return Object.values(value).reduce((n: number, v) => n + words(v), 0);
  return 0;
}

it.each([["es", es], ["en", en]])("keeps the %s copy within the A3 budgets: /producto 450 words, /ens 500", (_, messages) => {
  expect(words(messages.producto)).toBeLessThanOrEqual(450);
  expect(words(messages.ens)).toBeLessThanOrEqual(500);
  expect(words(messages.producto)).toBeGreaterThan(150);
  expect(words(messages.ens)).toBeGreaterThan(120);
});

it("turns both pages on in the site map, so menus link to them and never to a 404", () => {
  expect(PAGES.producto).toBe(true);
  expect(PAGES.ens).toBe(true);
  expect(LINKS.map((l) => l.href)).toContain("/ens");
  const hrefs = PRODUCT.flatMap((g) => g.items.map((i) => i.href));
  for (const anchor of ["autoevaluacion", "registros", "incidentes", "dossier", "asistente"]) expect(hrefs).toContain(`/producto#${anchor}`);
});

it("/producto has one section per capability at the menu anchors, each with a sample product view", () => {
  renderWithProviders(<Producto />);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  for (const id of ["autoevaluacion", "registros", "incidentes", "dossier", "asistente", "api"]) {
    const section = document.getElementById(id);
    expect(section?.tagName, id).toBe("SECTION");
    expect(within(section as HTMLElement).getByRole("heading", { level: 2 })).toBeTruthy();
    expect(within(section as HTMLElement).getByRole("figure").textContent).toContain("Datos de ejemplo");
  }
});

it("the assistant view quotes the ENS pack's reviewed evidence, with its guide citation", () => {
  type Req = { id: string; attributes: { expected_evidence: { reviewed_by?: string; items: { es: string; en: string; ref: { guide: string; section: string; page: number } }[] } } };
  const pack = load(readFileSync(join(CATALOG, "frameworks/ens_rd311_2022/requirements.yaml"), "utf8")) as { requirements: Req[] };
  const measure = pack.requirements.find((r) => r.id === fixture.assistant.code)!;
  expect(measure.attributes.expected_evidence.reviewed_by).toBeTruthy();
  const items = measure.attributes.expected_evidence.items.slice(0, fixture.assistant.items.length);
  expect(fixture.assistant.items).toEqual(items.map(({ es, en }) => ({ es, en })));
  const ref = items[0]!.ref;
  expect(fixture.assistant.cite).toBe(`${ref.guide} · ${ref.section} · p. ${ref.page}`);
  renderWithProviders(<Producto />);
  const view = within(document.getElementById("asistente") as HTMLElement).getByRole("figure");
  expect(view.textContent).toContain(fixture.assistant.items[0]!.es);
  expect(view.textContent).toContain(fixture.assistant.cite);
});

it("the API view names only real MCP tools", () => {
  renderWithProviders(<Producto />);
  const view = within(document.getElementById("api") as HTMLElement).getByRole("figure");
  const real = new Set([...MCP_TOOLS.read, ...MCP_TOOLS.write].map((tool) => tool.name));
  const named = [...view.querySelectorAll("[data-tool]")].map((el) => el.getAttribute("data-tool"));
  expect(named.length).toBeGreaterThan(0);
  for (const name of named) expect(real.has(name as string), name as string).toBe(true);
});

it("reads the 73 ENS measures, their group titles and rules from the catalog pack", () => {
  const catalog = loadEnsCatalog(CATALOG);
  const measures = catalog.frameworks.flatMap((f) => f.groups.flatMap((g) => g.measures));
  expect(measures).toHaveLength(73);
  expect(catalog.frameworks.map((f) => f.title)).toEqual(["Marco organizativo", "Marco operacional", "Medidas de protección"]);
  expect(catalog.frameworks[1]!.groups.map((g) => g.prefix)).toEqual(["op.pl", "op.acc", "op.exp", "op.ext", "op.nub", "op.cont", "op.mon"]);
  for (const m of measures) {
    expect(m.source, m.code).toMatch(/^https:\/\/www\.boe\.es\//);
    expect(m.rules, m.code).toHaveLength(3);
  }
  expect(measures.find((m) => m.code === "org.1")).toMatchObject({ title: "Política de seguridad", dimensions: "Todas", rules: ["aplica", "aplica", "aplica"] });
});

it("/ens lists all 73 measures with Spanish titles, BOE links and scrollable, labelled tables", async () => {
  renderWithProviders(<EnsPage catalog={loadEnsCatalog(CATALOG)} />);
  expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  const rows = document.querySelectorAll(".ens-measures tbody tr");
  expect(rows).toHaveLength(73);
  for (const row of rows) {
    expect(row.querySelector("a")?.getAttribute("href")).toMatch(/^https:\/\/www\.boe\.es\//);
    expect(row.querySelector("[lang=es]")).toBeTruthy();
  }
  for (const region of document.querySelectorAll(".ens-table")) {
    expect(region.getAttribute("tabindex")).toBe("0");
    expect(region.getAttribute("role")).toBe("region");
    expect(region.getAttribute("aria-label")).toBeTruthy();
  }
});

it("/ens embeds the assistant's category flow, which answers with its citations", async () => {
  renderWithProviders(<EnsPage catalog={loadEnsCatalog(CATALOG)} />);
  const groups = await screen.findAllByRole("radiogroup");
  expect(groups).toHaveLength(5);
  for (const group of groups) fireEvent.click(within(group).getAllByRole("radio")[1]!);
  expect(await screen.findByText(/MEDIA/, { selector: ".assistant-result-title" })).toBeTruthy();
});
