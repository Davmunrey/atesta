// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RecordsGlance } from "@/components/records-glance";
import { overdueTrainings } from "@/lib/summaries";
import { renderWithProviders, stubApi } from "./render";

// Records at a glance on the overview (ui-polish spec, issue 287).
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const owner = { organization_id: "primary", organization_name: "Synthetic Team", role: "owner" as const, access_expires_on: null, closure_erase_after: null };
const base = "/api/v1/orgs/primary";
const campaign = (id: string, closes: string, closed: boolean) => ({ id, title: id, material_url: "https://example.com", closes_on: closes, created_at: "2026-11-01T00:00:00Z", closed_at: closed ? "2026-11-02T00:00:00Z" : null, acknowledged: 1 });

it("counts open trainings past their closing date", () => {
  expect(overdueTrainings([campaign("a", "2026-11-01", false), campaign("b", "2026-11-01", true), campaign("c", "2026-12-01", false)], "2026-11-23")).toBe(1);
});

it("lists policies, access reviews, training and incidents in order, each with a written state and its summary", async () => {
  stubApi({
    [`GET ${base}/policies`]: [200, [{ id: "p", title: "p", location_url: "https://example.com/p", review_months: 12, created_at: "2026-01-01T00:00:00Z", latest: null, next_review_on: null }]],
    [`GET ${base}/access-reviews`]: [200, []],
    [`GET ${base}/training-campaigns`]: [200, [campaign("t", "2999-01-01", false)]],
    [`GET ${base}/incidents`]: [500, { error: { code: "internal" } }],
  });
  renderWithProviders(<RecordsGlance org={owner} />);
  const table = await screen.findByRole("table", { name: "Registros" });
  await vi.waitFor(() => { if (within(table).queryAllByText("Cargando…").length > 0) throw new Error("still loading"); });
  const rows = within(table).getAllByRole("row").slice(1).map((row) => [...row.querySelectorAll("th, td")].map((cell) => cell.textContent));
  expect(rows).toEqual([
    ["Políticas", "Requiere acción", "1 política sin aprobar."],
    ["Revisiones de acceso", "Sin registros", "Aún no hay revisiones de acceso."],
    ["Formación", "Al día", "Las formaciones abiertas están en plazo."],
    ["Incidentes", "—", "No se pudo cargar."],
  ]);
  expect(within(table).getByRole("link", { name: "Políticas" }).getAttribute("href")).toBe("/app/policies?org=primary");
  expect(within(table).getByRole("link", { name: "Incidentes" }).getAttribute("href")).toBe("/app/incidents?org=primary");
});
