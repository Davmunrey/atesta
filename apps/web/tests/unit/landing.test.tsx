// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, screen, within } from "@testing-library/react";
import { load } from "js-yaml";
import { afterEach, expect, it, vi } from "vitest";
import { LandingPage } from "@/components/landing/landing-page";
import { IncidentView } from "@/components/landing/moment-views";
import { PublicHeader } from "@/components/public-header";
import { legalEntity } from "@/content/legal-entity";
import fixture from "@/content/landing-fixture.json";
import { loadLandingCatalog } from "@/lib/catalog/landing";
import en from "../../messages/en.json";
import es from "../../messages/es.json";
import { legalIssues } from "../../scripts/check-legal";
import { renderWithProviders } from "./render";

// Landing (landing-legal spec, L6; amendment A4, issue 393: one story, told once).
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
afterEach(cleanup);

const WEB = join(import.meta.dirname, "../..");
const CATALOG = join(WEB, "../../catalog");
const catalog = loadLandingCatalog(CATALOG);
const landing = (locale: "es" | "en" = "es") => renderWithProviders(<LandingPage catalog={catalog} />, locale);
const yaml = <T,>(path: string) => load(readFileSync(join(CATALOG, path), "utf8")) as T;
type Requirement = { id: string; title_es: string; source: string; attributes: Record<string, unknown> };
const requirement = (pack: string, id: string) => yaml<{ requirements: Requirement[] }>(`frameworks/${pack}/requirements.yaml`).requirements.find((r) => r.id === id)!;

function words(value: unknown): number {
  if (typeof value === "string") return value.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w)).length;
  if (value && typeof value === "object") return Object.entries(value).filter(([key]) => key !== "view").reduce((n, [, v]) => n + words(v), 0);
  return 0;
}

// Amendment A3 (accepted by the owner, 2026-11-23): up to 260 words of landing copy.
it.each([["es", es], ["en", en]])("keeps the %s marketing copy within 260 words, product views excluded", (_, messages) => {
  expect(words(messages.landing)).toBeLessThanOrEqual(260);
  expect(words(messages.landing)).toBeGreaterThan(120);
});

it("tells the story once: hero, problem, how it works, other frameworks, close", () => {
  landing();
  expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
    "Qué pide el ENS a tu empresa", "Cómo funciona", "Si además te aplica NIS2, el RGPD o DORA",
    "Escríbenos y te enseñamos Atesta en una llamada",
  ]);
  expect(screen.queryByText("Un año de ENS")).toBeNull();
  expect(screen.queryByRole("tablist")).toBeNull();
  expect(screen.queryByRole("button", { name: /animación/i })).toBeNull();
  expect(document.querySelector(".frameworks-ring, .landing-marquee, .landing-stage-counter")).toBeNull();
  // The proof strip lives in the footer only, once per page.
  expect(screen.queryByRole("list", { name: "Lo que es verdad hoy" })).toBeNull();
});

it("leads with the ENS and asks for access by email", () => {
  landing();
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Prepara el ENS sin un consultor a tiempo completo");
  expect(screen.getByRole("heading", { level: 1 }).querySelector("mark")!.textContent).toBe("ENS");
  const requests = screen.getAllByRole("link", { name: "Solicitar acceso" });
  expect(requests.length).toBeGreaterThan(0);
  for (const link of requests) expect(link.getAttribute("href")).toBe(`mailto:${legalEntity.email}`);
});

it("shows one real ENS measure in the hero, from the catalog, with its BOE source and the clause highlighted", () => {
  landing();
  const hero = screen.getByRole("heading", { level: 1 }).closest("section")!;
  const measure = requirement("ens_rd311_2022", catalog.measure.code);
  const official = String(measure.attributes.official_text_es);
  const doc = within(hero).getByRole("article", { name: /op\.acc\.6/ });
  expect(doc.querySelector(".official-text")!.getAttribute("lang")).toBe("es");
  expect(within(doc).getByText(measure.title_es)).toBeTruthy();
  for (const p of catalog.measure.paragraphs) expect(official).toContain(p);
  expect(official).toContain(catalog.measure.paragraphs.join("\n\n"));
  const clause = doc.querySelector("mark")!;
  expect(clause.textContent).toBe(catalog.measure.paragraphs.at(-1));
  expect(clause.textContent).toContain("[op.acc.6.r8.1]");
  expect(within(doc).getByRole("link", { name: /BOE/ }).getAttribute("href")).toBe(measure.source);
  // The self-assessment beside it is sample data, labelled once; the law is not.
  expect(within(hero).getAllByText("Datos de ejemplo")).toHaveLength(1);
  expect(within(doc).queryByText("Datos de ejemplo")).toBeNull();
  expect(hero.querySelector(".lv-kpis, [role='tablist']")).toBeNull();
});

it("reads the hero's proposal and expected evidence from the catalog's reviewed content", () => {
  const measure = requirement("ens_rd311_2022", "op.acc.6");
  const rules = measure.attributes.selection_rules as { level: string; rule: string }[];
  expect(catalog.measure.rule).toBe(rules.find((r) => r.level === "MEDIO")!.rule);
  const expected = measure.attributes.expected_evidence as { reviewed_by: string; items: unknown[] };
  expect(expected.reviewed_by).toBeTruthy();
  expect(catalog.measure.evidence).toEqual(expected.items);
  landing();
  const hero = screen.getByRole("heading", { level: 1 }).closest("section")!;
  for (const item of catalog.measure.evidence) expect(within(hero).getByText(item.es)).toBeTruthy();
  // The console's own labels (register, expected evidence), with the team instead of a person.
  expect(within(hero).getByText("Tu autoevaluación")).toBeTruthy();
  // The page outline stays whole: no heading inside the hero skips from h1 to h3.
  expect(hero.querySelector("h3, h4")).toBeNull();
  expect(hero.textContent).toContain("Propuesta según las tablas oficiales: Aplica");
  expect(hero.textContent).toContain("revisada por el equipo de Atesta");
  expect(hero.textContent).not.toMatch(/Muñoz/);
});

it("maps one common control to ENS, NIS2, RGPD and DORA from signed mappings only, without the reviewer's name", () => {
  const packs = ["ens_rd311_2022", "nis2", "gdpr_art32", "dora"];
  const signed = packs.map((pack) => yaml<{ mappings: { requirement_id: string; control_id: string; reviewed_by: string | null }[] }>(`frameworks/${pack}/mappings.yaml`)
    .mappings.filter((m) => m.control_id === catalog.mapping.control.id && m.reviewed_by).map((m) => m.requirement_id));
  expect(catalog.mapping.rows.map((r) => r.framework)).toEqual(packs);
  catalog.mapping.rows.forEach((row, i) => {
    expect(signed[i]).toContain(row.id);
    const source = requirement(row.framework, row.id);
    expect(row.title_es).toBe(source.title_es);
    expect(row.source).toBe(source.source);
  });
  landing();
  const table = screen.getByRole("table");
  expect(within(table).getByText(catalog.mapping.control.title_es, { exact: false })).toBeTruthy();
  const rows = within(table).getAllByRole("row").slice(1);
  expect(rows.map((r) => within(r).getByRole("rowheader").textContent)).toEqual(["ENS", "NIS2", "RGPD", "DORA"]);
  expect(rows[0]!.querySelector("a")!.getAttribute("href")).toBe(catalog.mapping.rows[0]!.source);
  expect(screen.getByRole("main").textContent).not.toMatch(/Muñoz|según (?:el|tu) plan/i);
});

it("runs the steps from assessing to the dossier, with the connect step last and coming soon", () => {
  landing();
  const how = screen.getByRole("heading", { level: 2, name: "Cómo funciona" }).closest("section")!;
  const steps = [...how.querySelectorAll(".landing-steps > li")] as HTMLElement[];
  expect(steps.map((s) => s.dataset.key)).toEqual(["assess", "routines", "incidents", "dossier", "connect"]);
  for (const step of steps.slice(0, 4)) expect(within(step).queryByText("Próximamente")).toBeNull();
  expect(within(steps[4]!).getByText("Próximamente")).toBeTruthy();
  expect(steps[4]!.querySelector("figure")).toBeNull();
  // One sample-data notice for the section, not one per frame.
  expect(within(how).getAllByText("Datos de ejemplo")).toHaveLength(1);
  const frame = how.querySelector(".landing-stage-frame")!;
  expect(frame.getAttribute("aria-hidden")).toBe("true");
  expect([...frame.querySelectorAll("[data-stage-view]")].map((el) => el.getAttribute("data-stage-view"))).toEqual(["assess", "routines", "incidents", "dossier"]);
});

it("shows the ENS incident duty, art. 33.7 of RD 311/2022, with no invented deadline", () => {
  renderWithProviders(<IncidentView />);
  const view = screen.getByRole("figure");
  expect(view.textContent).toContain("art. 33.7");
  expect(view.textContent).toContain("INCIBE-CERT");
  expect(view.textContent).not.toMatch(/NIS2|2022\/2555|Vence|\b\d+ ?h\b/);
  expect(view.querySelector(".li-bar, .li-clock")).toBeNull();
});

it("closes by saying what happens after writing to us", () => {
  landing();
  const close = screen.getByRole("heading", { level: 2, name: "Escríbenos y te enseñamos Atesta en una llamada" }).closest("section")!;
  expect(within(close).getByText(/medidas del ENS que aplican a tu categoría/)).toBeTruthy();
  expect(within(close).getByRole("link", { name: "Solicitar acceso" }).getAttribute("href")).toBe(`mailto:${legalEntity.email}`);
});

it("renders the English landing completely", () => {
  landing("en");
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Get ENS-ready without a full-time consultant");
  expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(4);
  expect(within(screen.getByRole("table")).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["ENS", "NIS2", "GDPR", "DORA"]);
});

// The critique's lines (A4): a sober, direct tone has no taglines, puns or plan wording.
const BANNED = [
  "El ENS no cabe en una hoja de cálculo", "Tu próxima auditoría, preparada", "Míralo con tus propias medidas",
  "Lo que Atesta puede tocar", "Sin fuente, no hay respuesta", "Según el plan", "según tu plan", "Un año de ENS",
  "does not fit in a spreadsheet", "Your next audit, prepared", "See it with your own measures", "What Atesta can touch, ",
  "No source, no answer", "By plan", "more by plan", "A year of ENS",
];
it.each([["es", es], ["en", en]])("keeps the replaced lines out of the %s messages", (_, messages) => {
  const text = JSON.stringify(messages);
  for (const line of BANNED) expect(text, line).not.toContain(line);
});

it("never breaks body text inside a word, and keeps figures and headlines in their limits", () => {
  const globals = readFileSync(join(WEB, "src/app/globals.css"), "utf8");
  const css = readFileSync(join(WEB, "src/styles/landing.css"), "utf8");
  const tokens = readFileSync(join(WEB, "src/styles/tokens.css"), "utf8");
  // Public pages break a word only when it cannot fit; the console keeps `anywhere` for long names.
  expect(globals).toMatch(/\.landing :is\(h1, h2, p, li\) \{ overflow-wrap: break-word; \}/);
  expect(globals).toMatch(/text-wrap: pretty/);
  // KPI suffixes are small through their own class; the figure keeps its size.
  expect(css).not.toMatch(/\.lv-kpis dd span \{/);
  // Nothing overshoots: no cubic-bezier with a y control point above 1.
  for (const [, , y1, , y2] of tokens.matchAll(/cubic-bezier\(([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+)\)/g)) {
    expect(Number(y1)).toBeLessThanOrEqual(1);
    expect(Number(y2)).toBeLessThanOrEqual(1);
  }
  // The hero headline stops at 5rem (DESIGN.md).
  for (const [, max] of css.matchAll(/\.landing-title[^{]*\{[^}]*font-size: clamp\([^,]+,[^,]+, ([\d.]+)rem\)/g)) expect(Number(max)).toBeLessThanOrEqual(5);
});

it("names every ENS measure in the product views exactly as the catalog does", () => {
  const ens = yaml<{ requirements: Requirement[] }>("frameworks/ens_rd311_2022/requirements.yaml").requirements;
  const names = new Map(ens.map((r) => [r.id, r.title_es]));
  expect(fixture.origin).toBe("illustrative");
  for (const item of fixture.attention) expect(names.get(item.code), item.code).toBe(item.title_es);
  expect(fixture.counts.total).toBe(names.size);
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
