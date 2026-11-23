// @vitest-environment jsdom
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ColumnChart, LineChart } from "@/components/charts";
import { renderWithProviders } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const components = join(__dirname, "../../src/components");
const source = (name: string) => readFileSync(join(components, name), "utf8");

// Phones (#238): a table stacks into rows below 36rem and each cell names its column from data-label.
it.each(readdirSync(components).filter((f) => f.endsWith(".tsx") && source(f).includes("table-region")))(
  "every data cell in %s names its column for the stacked layout",
  (file) => {
    const cells = source(file).match(/<td\b[^>]*>/g) ?? [];
    expect(cells.length).toBeGreaterThan(0);
    expect(cells.filter((cell) => !cell.includes("data-label="))).toEqual([]);
  },
);

it("stacks tables by their own width, with the column name before each value", () => {
  const css = readFileSync(join(__dirname, "../../src/styles/console.css"), "utf8");
  expect(css).toMatch(/\.table-region\s*\{[^}]*container-type:\s*inline-size/);
  expect(css).toMatch(/@container \(width < 36rem\)/);
  expect(css).toContain("content: attr(data-label)");
});

it.each([
  ["line", () => <LineChart title="Implantadas" valueLabel="Implantadas" periodLabel="Día" tableLabel="Ver tabla" points={[{ label: "1 nov", value: 1 }, { label: "2 nov", value: 3 }]} />],
  ["column", () => <ColumnChart title="Acciones" valueLabel="Acciones" periodLabel="Día" tableLabel="Ver tabla" points={[{ label: "1 nov", value: 2 }]} />],
])("the %s chart's table names both columns", (_kind, chart) => {
  renderWithProviders(chart());
  const headers = within(screen.getByRole("table")).getAllByRole("columnheader").map((th) => th.textContent);
  expect(headers).toEqual(["Día", expect.stringMatching(/^(Implantadas|Acciones)$/)]);
});

it("draws charts at their real width, so axis text keeps its size on a phone", () => {
  let report: (entries: { contentRect: { width: number } }[]) => void = () => {};
  vi.stubGlobal("ResizeObserver", class { constructor(cb: typeof report) { report = cb; } observe() {} disconnect() {} });
  renderWithProviders(<ColumnChart title="Acciones" valueLabel="Acciones" periodLabel="Día" tableLabel="Ver tabla" points={[{ label: "1 nov", value: 2 }]} />);
  report([{ contentRect: { width: 320 } }]);
  return vi.waitFor(() => expect(screen.getByRole("img", { name: "Acciones" }).getAttribute("viewBox")).toBe("0 0 320 220"));
});
