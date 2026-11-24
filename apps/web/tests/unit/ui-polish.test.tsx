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
  const css = readFileSync(join(__dirname, "../../../../packages/ui/src/styles/components.css"), "utf8");
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

// Readable activity (#239): every action the API records has a label in both languages.
const API = join(__dirname, "../../../api/src/atesta_api");
function apiFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? apiFiles(join(dir, e.name)) : e.name.endsWith(".py") ? [join(dir, e.name)] : []);
}
const recorded = () => {
  const text = apiFiles(API).map((f) => readFileSync(f, "utf8")).join("\n");
  const literal = [...text.matchAll(/action="([a-z_]+\.[a-z_]+)"/g)].map((m) => m[1]!);
  // Actions built at run time: scan statuses, connection verdicts and incident update kinds.
  const built = [
    ...["succeeded", "partial", "failed", "blocked"].map((s) => `scan.${s}`),
    ...["verified", "incomplete", "over_privileged", "revoked"].map((v) => `connection.${v}`),
    ...["note", "clock_met", "closed"].map((k) => `incident.${k}`),
  ];
  expect(text).toContain('action=f"scan.{status}"');
  expect(text).toContain('action=f"connection.{action}"');
  expect(text).toContain("action=f\"incident.{'clock_met' if body.kind == 'clock' else body.kind}\"");
  return [...new Set([...literal, ...built])].sort();
};

it.each(["es", "en"] as const)("labels every audit action the API records in %s", async (locale) => {
  const messages = (await import(`../../messages/${locale}.json`)).default as { activity: { actions: Record<string, string> } };
  const missing = recorded().filter((action) => !(action.replaceAll(".", "_") in messages.activity.actions));
  expect(recorded().length).toBeGreaterThan(40);
  expect(missing).toEqual([]);
});

it("never shows an action code or a UUID: unknown actions get a generic label, ids are dropped", async () => {
  const { activityLabel, activityTarget } = await import("@/lib/activity");
  const t = Object.assign((key: string) => ({ "actions.org_created": "Creó la organización", unknown: "Otra acción" })[key] ?? key, { has: (key: string) => key === "actions.org_created" });
  expect(activityLabel(t, "org.created")).toBe("Creó la organización");
  expect(activityLabel(t, "future.thing")).toBe("Otra acción");
  expect(activityTarget("4f09a132-912e-4d79-ab3b-03c0e3a3e38a")).toBeNull();
  expect(activityTarget("ens_rd311_2022:mp.s.4")).toBe("ens_rd311_2022:mp.s.4");
  expect(activityTarget(null)).toBeNull();
});

it("shows every self-assessment state with a drawn icon beside its label", async () => {
  const { StateBadge } = await import("@/components/self-assessment");
  const base = { code: "a.1", title_es: "a", title_en: null, selection_basis: null, proposal: { decision: "undecided" as const, rule: null, level: null }, assignment: null };
  const assessed = (implementation: "implemented" | "partially_implemented" | "not_implemented", applicability: "applies" | "not_applicable" = "applies") => ({
    applicability, implementation, regularly_reviewed: false, justification: "", performed_by: "", performed_on: null, evidence_statement_ids: [], notes: "", recorded_by: "u", recorded_at: "2026-11-20T10:00:00Z",
  });
  const items = [{ ...base, assessment: null }, { ...base, assessment: assessed("implemented") }, { ...base, assessment: assessed("partially_implemented") },
    { ...base, assessment: assessed("not_implemented") }, { ...base, assessment: assessed("not_implemented", "not_applicable") }];
  renderWithProviders(<>{items.map((item, i) => <StateBadge key={i} item={item} />)}</>);
  const badges = [...document.querySelectorAll(".requirement-state")];
  expect(badges.map((b) => b.textContent)).toEqual(["Pendiente", "Implantada", "Implantada en parte", "No implantada", "No aplica"]);
  for (const badge of badges) expect(badge.querySelector("svg[aria-hidden=true]")).not.toBeNull();
  expect(new Set(badges.map((b) => b.querySelector("svg")!.innerHTML)).size).toBe(5);
});

it("never nests a panel: evidence totals are a ruled row inside the collections panel", () => {
  const css = readFileSync(join(__dirname, "../../src/styles/console.css"), "utf8");
  const panels = css.match(/\.console :is\(([^)]*)\) \{/)![1]!;
  expect(panels).toContain(".collection-summary");
  expect(panels).not.toContain(".evidence-summary");
});
