// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useState } from "react";
import { FrameworkLedger } from "@/components/framework-ledger";
import { OverviewDashboard } from "@/components/overview-dashboard";
import { ScanHistory } from "@/components/scan-history";
import { emptyOverview, overview } from "../fixtures/overview";
import { renderWithProviders, stubApi } from "./render";

const path = "GET /api/v1/orgs/primary/overview";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("links to the requirement register with organization and framework context", async () => {
  stubApi({ [path]: [200, overview] });
  renderWithProviders(<OverviewDashboard orgId="primary" />);
  const link = await screen.findByRole("link", { name: "Synthetic Alpha" });
  expect(link.getAttribute("href")).toBe("/app/framework?org=primary&framework=synthetic_alpha");
  cleanup();
  // The Marcos page keeps the full ledger (console-unification spec moved it off the home).
  renderWithProviders(<FrameworkLedger frameworks={overview.frameworks} orgId="primary" headless />);
  expect(screen.getAllByRole("link", { name: "Ver requisitos y configuración" })[0]!.getAttribute("href")).toBe("/app/framework?org=primary&framework=synthetic_alpha");
});

it("explains an empty organization without inventing a score or scan action", async () => {
  stubApi({ [path]: [200, emptyOverview] });
  renderWithProviders(<OverviewDashboard orgId="primary" />);
  expect(await screen.findByText("Todavía no hay marcos publicados")).toBeTruthy();
  // An empty collection panel teaches nothing; it appears once a scan or evidence exists.
  expect(screen.queryByText("Aún no hay análisis registrados")).toBeNull();
  expect(screen.queryByText(/%/)).toBeNull();
  expect(screen.queryByRole("button", { name: /Iniciar análisis|Exportar/ })).toBeNull();
});

it("distinguishes zero, unscored and missing snapshots, retaining recorded provenance", async () => {
  renderWithProviders(<><FrameworkLedger frameworks={overview.frameworks} orgId="primary" headless />
    <ScanHistory scans={overview.scans} evidenceCount={overview.evidence_count} /></>);
  const alpha = (await screen.findByText("Synthetic Alpha")).closest("details")!;
  expect(screen.getByText("0 %")).toBeTruthy();
  expect(screen.getByText("Sin puntuación")).toBeTruthy();
  expect(screen.getByText("1 marco en preparación, aún sin requisitos")).toBeTruthy();
  fireEvent.click(within(alpha).getByText("Synthetic Alpha"));
  expect(within(alpha).getByText("synthetic-1")).toBeTruthy();
  expect(within(alpha).getByText("Organización completa")).toBeTruthy();
  expect(screen.getByText("7 de 10 comprobaciones evaluadas")).toBeTruthy();
  expect(screen.getByText("Bloqueado")).toBeTruthy();
  cleanup();
  stubApi({ [path]: [200, overview] });
  renderWithProviders(<OverviewDashboard orgId="primary" />);
  expect(await screen.findByText("Entorno de desarrollo")).toBeTruthy();
  expect(screen.getByText(/^Último análisis: 66,7/)).toBeTruthy();
  expect(screen.getByText("Último análisis sin puntuación")).toBeTruthy();
});

it("offers search only once there are more frameworks than a glance covers", async () => {
  stubApi({ [path]: [200, overview] });
  renderWithProviders(<OverviewDashboard orgId="primary" />);
  await screen.findByText("Synthetic Alpha");
  expect(screen.queryByRole("searchbox", { name: "Buscar marco" })).toBeNull();
});

it("filters frameworks and clears an empty result", async () => {
  const extra = Array.from({ length: 5 }, (_, i) => ({ ...overview.frameworks[3]!, key: `synthetic_extra_${i}`, name: `Synthetic Extra ${i}` }));
  renderWithProviders(<FrameworkLedger frameworks={[...overview.frameworks, ...extra]} orgId="primary" headless />);
  const input = await screen.findByRole("searchbox", { name: "Buscar marco" });
  fireEvent.change(input, { target: { value: " ALPHA " } });
  expect(screen.queryByText("Synthetic Beta")).toBeNull();
  expect(screen.getByText("Synthetic Alpha")).toBeTruthy();
  fireEvent.change(input, { target: { value: "absent" } });
  expect(screen.getByText("Ningún marco coincide con la búsqueda")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Limpiar búsqueda" }));
  expect(screen.getByText("Synthetic Beta")).toBeTruthy();
});

it("lets the user retry a failed read", async () => {
  stubApi({ [path]: [[503, { detail: { code: "auth.provider_unavailable" } }], [200, emptyOverview]] });
  renderWithProviders(<OverviewDashboard orgId="primary" />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
  expect(await screen.findByText("Todavía no hay marcos publicados")).toBeTruthy();
});

it("refreshes the current organization through the API", async () => {
  const requests = stubApi({ [path]: [[200, overview], [200, emptyOverview]] });
  renderWithProviders(<OverviewDashboard orgId="primary" />);
  await screen.findByText("Synthetic Alpha");
  fireEvent.click(screen.getByRole("button", { name: "Actualizar resultados" }));
  expect(await screen.findByText("Todavía no hay marcos publicados")).toBeTruthy();
  // First steps reads the register separately; count only the overview requests.
  expect(requests.filter((r) => new URL(r.url).pathname.endsWith("/overview"))).toHaveLength(2);
});

it("shows a loading state instead of another organization's results", async () => {
  stubApi({ [path]: [200, overview] });
  function Switcher() {
    const [orgId, setOrgId] = useState("primary");
    return <><button onClick={() => setOrgId("secondary")}>Switch organization</button><OverviewDashboard key={orgId} orgId={orgId} /></>;
  }
  renderWithProviders(<Switcher />);
  await screen.findByText("Synthetic Alpha");
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  fireEvent.click(screen.getByRole("button", { name: "Switch organization" }));
  expect(screen.getByRole("status").textContent).toContain("Cargando resultados");
  expect(screen.queryByText("Synthetic Alpha")).toBeNull();
});
