// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FrameworkDetailView } from "@/components/framework-detail";
import { framework, preparationFramework, requirementGuidance } from "../fixtures/framework";
import { renderWithProviders, stubApi } from "./render";

const path = "GET /api/v1/orgs/primary/frameworks/synthetic_alpha";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const render = () => renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" />);

it("explains template boundaries and offers preparation without fabricating coverage", async () => {
  stubApi({ [path]: [200, preparationFramework] }); render();
  expect(await screen.findByRole("heading", { name: "Plantilla de preparación" })).toBeTruthy();
  expect(screen.getByText(/Puntuación automática desactivada/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "0 requisitos disponibles" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "1 guía de preparación" }).getAttribute("href")).toBe("#preparation-controls-heading");
  expect(screen.getByText("Faltan requisitos y mapeos revisados.")).toBeTruthy();
  expect(screen.getByText("synthetic_access_check")).toBeTruthy();
  expect(screen.queryByText(/%/)).toBeNull();
});

it("shows official selection rules separately from recorded status", async () => {
  stubApi({ [path]: [200, { ...framework, requirements: [{ ...framework.requirements[0], guidance: requirementGuidance }] }] }); render();
  expect(await screen.findByRole("table")).toBeTruthy();
  expect(screen.getByRole("rowheader", { name: "BAJO" })).toBeTruthy();
  expect(screen.getByText("+ [R1 o R2]")).toBeTruthy();
  expect(screen.getByText(requirementGuidance.official_text_es).getAttribute("lang")).toBe("es");
  expect(within(document.querySelector("details.requirement-row")!).getByText("No superado")).toBeTruthy();
});

it("prioritizes failures and open work before passed requirements", async () => {
  stubApi({ [path]: [200, { ...framework, requirements: [...framework.requirements].reverse() }] }); render();
  await screen.findByRole("heading", { level: 1, name: framework.name });
  const rows = Array.from(document.querySelectorAll("details.requirement-row"));
  expect(rows.map((row) => row.querySelector("summary .requirement-code")?.textContent)).toEqual(["R1", "R2", "R3", "R4", "OLD"]);
  expect(rows[0]?.getAttribute("open")).toBe("");
});

it("separates recorded states, current guidance and missing observations", async () => {
  stubApi({ [path]: [200, framework] }); render();
  expect(await screen.findByRole("heading", { level: 1, name: "Synthetic Alpha" })).toBeTruthy();
  expect(screen.getByText(/El catálogo ha cambiado/)).toBeTruthy();
  const row = screen.getByText("Protección de cuentas de prueba").closest("details")!;
  expect(within(row).getByText("No superado")).toBeTruthy();
  expect(within(row).getAllByText("Sin observación").length).toBeGreaterThan(0);
  expect(within(row).getByText(framework.requirements[0]!.controls[0]!.description_es)).toBeTruthy();
  expect(within(row).getByRole("link", { name: "example.test · guide" }).getAttribute("href")).toBe("https://example.test/guide");
  expect(within(row).queryByRole("link", { name: "javascript:alert(1)" })).toBeNull();
  expect(screen.getByText("Requisito histórico sin ficha actual")).toBeTruthy();
});

it("filters gaps by state and searches requirement and configuration text", async () => {
  stubApi({ [path]: [200, framework] }); render();
  const filter = await screen.findByRole("button", { name: "No superado 1" });
  fireEvent.click(filter);
  expect(filter.getAttribute("aria-pressed")).toBe("true");
  expect(screen.queryByText("Registro comprobado")).toBeNull();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "synthetic_access_check" } });
  expect(screen.getByText("Protección de cuentas de prueba")).toBeTruthy();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "absent" } });
  expect(screen.getByText("Ningún requisito coincide")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Limpiar filtros" }));
  expect(screen.getByText("Registro comprobado")).toBeTruthy();
});

it("explains an empty unassessed framework without a fabricated percentage", async () => {
  stubApi({ [path]: [200, { ...framework, snapshot: null, requirements: [] }] }); render();
  expect(await screen.findByText("Este marco aún no tiene requisitos disponibles")).toBeTruthy();
  expect(screen.getByText("Todavía no hay una evaluación registrada para este marco.")).toBeTruthy();
  expect(screen.queryByText(/%/)).toBeNull();
});

it("recovers after a failed read and refreshes the same framework", async () => {
  const requests = stubApi({ [path]: [[503, {}], [200, framework]] }); render();
  expect(await screen.findByRole("alert")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findByRole("heading", { level: 1 })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Actualizar resultados" }));
  // The register is a separate read; count only the framework detail requests.
  expect(requests.filter((r) => new URL(r.url).pathname.endsWith("/frameworks/synthetic_alpha"))).toHaveLength(3);
});

it("shows loading while a framework read is pending", () => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {}))); render();
  expect(screen.getByRole("status").textContent).toContain("Cargando requisitos");
  expect(screen.queryByText("Synthetic Alpha")).toBeNull();
});

const expectedEvidence = { reviewed_by: null, items: [
  { es: "Registro de altas y bajas de cuentas.", en: "Record of accounts created and removed.", ref: { guide: "CCN-STIC 808", edition: "2026-04", section: "6.2.2.2 (op.acc.1)", page: 32 } },
] };

it("lists the evidence a guide expects under the requirement, cited and marked as a candidate", async () => {
  stubApi({ [path]: [200, { ...framework, requirements: [{ ...framework.requirements[0], guidance: { ...requirementGuidance, expected_evidence: expectedEvidence } }] }] }); render();
  const disclosure = (await screen.findByText(/Evidencias que propone la guía/)).closest("details")!;
  expect(disclosure.className).toContain("row-section");
  expect(within(disclosure).getByText("Registro de altas y bajas de cuentas.")).toBeTruthy();
  expect(within(disclosure).getByText("Referencia: CCN-STIC 808 (abril de 2026), apartado 6.2.2.2 (op.acc.1), pág. 32")).toBeTruthy();
  expect(within(disclosure).getByText(/Pendiente de revisión cualificada/)).toBeTruthy();
});

it("reads the expected evidence in English", async () => {
  stubApi({ [path]: [200, { ...framework, requirements: [{ ...framework.requirements[0], guidance: { ...requirementGuidance, expected_evidence: expectedEvidence } }] }] });
  renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" />, "en");
  expect(await screen.findByText("Record of accounts created and removed.")).toBeTruthy();
  expect(screen.getByText("Reference: CCN-STIC 808 (April 2026), section 6.2.2.2 (op.acc.1), p. 32")).toBeTruthy();
});

it("names the reviewer and the date once the owner signs the expected evidence", async () => {
  const signed = { ...expectedEvidence, reviewed_by: "David Muñoz", reviewed_on: "2026-11-23" };
  stubApi({ [path]: [200, { ...framework, requirements: [{ ...framework.requirements[0], guidance: { ...requirementGuidance, expected_evidence: signed } }] }] }); render();
  const disclosure = (await screen.findByText(/Evidencias que propone la guía/)).closest("details")!;
  expect(within(disclosure).getByText(/revisada por David Muñoz el 23 de noviembre de 2026/)).toBeTruthy();
  expect(within(disclosure).queryByText(/Pendiente de revisión/)).toBeNull();
});
