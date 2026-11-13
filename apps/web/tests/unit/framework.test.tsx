// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FrameworkDetailView } from "@/components/framework-detail";
import { framework } from "../fixtures/framework";
import { renderWithProviders, stubApi } from "./render";

const path = "GET /api/v1/orgs/primary/frameworks/synthetic_alpha";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const render = () => renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" />);

it("prioritizes failures and open work before passed requirements", async () => {
  stubApi({ [path]: [200, { ...framework, requirements: [...framework.requirements].reverse() }] }); render();
  await screen.findByRole("heading", { level: 1 });
  const rows = Array.from(document.querySelectorAll("details.requirement-row"));
  expect(rows.map((row) => row.querySelector("summary .requirement-code")?.textContent)).toEqual(["R1", "R2", "R3", "R4", "OLD"]);
  expect(rows[0]?.getAttribute("open")).toBe("");
});

it("separates recorded states, current guidance and missing observations", async () => {
  stubApi({ [path]: [200, framework] }); render();
  expect(await screen.findByRole("heading", { level: 1, name: "Synthetic Alpha" })).toBeTruthy();
  expect(screen.getByText(/El catálogo ha cambiado/)).toBeTruthy();
  const row = screen.getByText("Protección de cuentas de prueba").closest("details")!;
  expect(within(row).getByText("No cumple")).toBeTruthy();
  expect(within(row).getAllByText("Sin observación").length).toBeGreaterThan(0);
  expect(within(row).getByText(framework.requirements[0]!.controls[0]!.description_es)).toBeTruthy();
  expect(within(row).getByRole("link", { name: "https://example.test/guide" }).getAttribute("href")).toBe("https://example.test/guide");
  expect(within(row).queryByRole("link", { name: "javascript:alert(1)" })).toBeNull();
  expect(screen.getByText("Requisito histórico sin ficha actual")).toBeTruthy();
});

it("filters gaps by state and searches requirement and configuration text", async () => {
  stubApi({ [path]: [200, framework] }); render();
  const filter = await screen.findByRole("button", { name: "No cumple 1" });
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
  expect(requests).toHaveLength(3);
});

it("shows loading while a framework read is pending", () => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {}))); render();
  expect(screen.getByRole("status").textContent).toContain("Cargando requisitos");
  expect(screen.queryByText("Synthetic Alpha")).toBeNull();
});
