// @vitest-environment jsdom
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ExpectedEvidence } from "@/components/expected-evidence";
import { FrameworkDetailView } from "@/components/framework-detail";
import { MeasureView } from "@/components/landing/moment-views";
import type { Register } from "@/lib/api/register-hooks";
import { loadLandingCatalog } from "@/lib/catalog/landing";
import type { Role } from "@/lib/permissions";
import { framework, requirementGuidance } from "../fixtures/framework";
import { renderWithProviders, stubApi } from "./render";

// One measure view (console-unification spec, part 4, issue 426): the console and public pages
// render a measure through the same component.
afterEach(() => { cleanup(); vi.unstubAllGlobals(); window.location.hash = ""; });

const base = "/api/v1/orgs/primary/frameworks/synthetic_alpha";
const WEB = join(import.meta.dirname, "../..");
const catalog = loadLandingCatalog(join(WEB, "../../catalog"));
const evidence = { reviewed_by: null, items: [
  { es: "Registro de altas y bajas de cuentas.", en: "Record of accounts created and removed.", ref: { guide: "CCN-STIC 808", edition: "2026-04", section: "6.2.2.2", page: 32 } },
] };
const detail = { ...framework, snapshot: null, requirements: [{ ...framework.requirements[0]!, guidance: { ...requirementGuidance, official_text_es: "Primer párrafo.\n\nSegundo párrafo.", expected_evidence: evidence } }] };
const assessed = { applicability: "applies" as const, implementation: "partially_implemented" as const, regularly_reviewed: false, justification: "",
  performed_by: "", performed_on: null, evidence_statement_ids: [], notes: "Falta el portal.", recorded_by: "u", recorded_at: "2026-11-21T10:00:00Z" };
const register = (assessment: typeof assessed | null): Register => ({
  framework_key: "synthetic_alpha", framework_version: "2", catalog_version: "synthetic-2", axes: {}, scope: null, review: null,
  groups_es: [{ prefix: "R", title: "Requisitos sintéticos" }], term_labels: [], profiles: [], scope_guide: null,
  items: [{ code: "R1", title_es: "Protección de cuentas de prueba", title_en: null, selection_basis: null,
    proposal: { decision: "applies", rule: "+ R1", level: "MEDIO" }, assessment, assignment: null }],
});
const consoleRow = async (role: Role = "admin", assessment: typeof assessed | null = null) => {
  stubApi({ [`GET ${base}`]: [200, detail], [`GET ${base}/register`]: [200, register(assessment)], "GET /api/v1/orgs/primary/members": [200, []] });
  renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" role={role} userId="u-other" />);
  return vi.waitFor(() => {
    const row = document.querySelector<HTMLDetailsElement>("details.requirement-row");
    if (!row) throw new Error("no measure row yet");
    return row;
  }, { timeout: 3000 });
};

it("renders the console's measure as the shared sheet: the record beside the law", async () => {
  const row = await consoleRow();
  expect(row.classList.contains("measure-sheet")).toBe(true);
  expect(row.id).toBe("req-R1");
  const record = row.querySelector<HTMLElement>(".measure-sheet-body > .measure-sheet-record")!;
  const law = row.querySelector<HTMLElement>(".measure-sheet-body > .measure-sheet-law")!;
  expect(within(record).getByRole("heading", { name: "Tu autoevaluación" })).toBeTruthy();
  expect(within(record).getByText(/Evidencias que propone la guía/)).toBeTruthy();
  expect(within(law).getByRole("table")).toBeTruthy();
  const quote = law.querySelector("blockquote.official-text")!;
  expect(quote.getAttribute("lang")).toBe("es");
  expect([...quote.querySelectorAll("p")].map((p) => p.textContent)).toEqual(["Primer párrafo.", "Segundo párrafo."]);
  expect(within(law).getByRole("link", { name: "example.test · requirement" })).toBeTruthy();
  // The guide and the official text are the law column now, never a second disclosure.
  expect(screen.queryByText("Guía y texto oficial")).toBeNull();
  const below = row.querySelector(".requirement-body > .measure-sheet-body ~ details.row-section > summary");
  expect(below?.textContent).toMatch(/Configuración, evidencias y revisión/);
});

it("shows the same state badge, proposal and recorded fields in the public sample and the console", async () => {
  const row = await consoleRow("admin", assessed);
  const consoleBadge = row.querySelector("summary .requirement-state")!.outerHTML;
  const consoleProposal = within(row).getByText(/Propuesta según las tablas oficiales/).className;
  const consoleFields = [...row.querySelectorAll(".assessment-summary > div")].map((d) => d.outerHTML);
  cleanup();
  renderWithProviders(<MeasureView measure={catalog.measure} />);
  const sample = screen.getByRole("article", { name: /op\.acc\.6/ });
  expect(sample.classList.contains("measure-sheet")).toBe(true);
  expect(sample.querySelector(".measure-sheet-head .requirement-state")!.outerHTML).toBe(consoleBadge);
  expect(within(sample).getByText(/Propuesta según las tablas oficiales/).className).toBe(consoleProposal);
  const sampleFields = [...sample.querySelectorAll(".assessment-summary > div")].map((d) => d.outerHTML);
  // Same component, same markup: the console's applicability and implementation rows appear verbatim.
  expect(sampleFields).toEqual(expect.arrayContaining(consoleFields.slice(0, 2)));
});

it.each(["member", "auditor"] as const)("keeps the sheet read-only for a %s who does not own the measure", async (role) => {
  const row = await consoleRow(role);
  expect(within(row).queryByRole("button", { name: "Evaluar esta medida" })).toBeNull();
  expect(within(row).queryByRole("button", { name: "Cambiar" })).toBeNull();
  expect(within(row).getByText(/Una persona administradora puede registrar/)).toBeTruthy();
});

it("opens the measure a link points to (#req-<code>)", async () => {
  window.location.hash = "#req-R1";
  Element.prototype.scrollIntoView = vi.fn();
  const row = await consoleRow();
  await vi.waitFor(() => expect(row.open).toBe(true));
});

it("offers the expected evidence open on public pages, naming the Atesta team, and as a disclosure elsewhere", () => {
  renderWithProviders(<>
    <ExpectedEvidence evidence={{ ...evidence, reviewed_by: "Revisor", reviewed_on: "2026-11-23" }} variant="sample" />
    <ExpectedEvidence evidence={evidence} variant="print" />
  </>);
  const [sample, print] = [...document.querySelectorAll(".expected-evidence")];
  expect(sample!.tagName).toBe("DIV");
  expect(sample!.textContent).toContain("revisada por el equipo de Atesta");
  expect(sample!.textContent).not.toContain("Revisor");
  expect(print!.tagName).toBe("DETAILS");
  expect(print!.classList.contains("catalog-disclosure")).toBe(true);
});

it("keeps a measure's markup in the shared component only", () => {
  const dir = join(WEB, "src/components");
  const files = readdirSync(dir, { recursive: true, encoding: "utf8" }).filter((f) => f.endsWith(".tsx") && f !== "measure-sheet.tsx");
  for (const file of files) {
    const source = readFileSync(join(dir, file), "utf8");
    for (const marker of ['"requirement-heading"', '"assessment-summary"', "data-assessment=", "<blockquote"]) {
      expect(source.includes(marker), `${file} renders ${marker}`).toBe(false);
    }
  }
});
