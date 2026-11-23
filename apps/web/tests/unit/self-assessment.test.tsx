// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FrameworkDetailView } from "@/components/framework-detail";
import { FirstSteps } from "@/components/first-steps";
import { FrameworkLedger } from "@/components/framework-ledger";
import { referenceLabel } from "@/components/catalog-reference";
import { groupByPrefix, registerProgress, type Register } from "@/lib/api/register-hooks";
import { framework } from "../fixtures/framework";
import { overview } from "../fixtures/overview";
import { renderWithProviders, stubApi } from "./render";

const base = "/api/v1/orgs/primary/frameworks/synthetic_alpha";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

/** Synthetic register: one category axis, one dimension axis, never a real normative pack. */
const register: Register = {
  framework_key: "synthetic_alpha", framework_version: "2", catalog_version: "synthetic-2",
  axes: { tier: { keys: [], levels: ["LOW", "MID", "HIGH"] }, level: { keys: ["C", "I"], levels: ["L", "M", "H"] } },
  scope: null, review: null, groups_es: [{ prefix: "R", title: "Requisitos sintéticos" }], term_labels: [], profiles: [], scope_guide: null,
  items: [
    { code: "R1", title_es: "Protección de cuentas de prueba", title_en: null, selection_basis: "tier · Todas", proposal: { decision: "applies", rule: "+ R1", level: "MID" }, assessment: null, assignment: null },
    { code: "R2", title_es: "Registro de revisión", title_en: null, selection_basis: "tier · Todas", proposal: { decision: "not_applicable", rule: "n.a.", level: "MID" }, assessment: null, assignment: null },
    { code: "R3", title_es: "Configuración pendiente de evaluar", title_en: null, selection_basis: null, proposal: { decision: "undecided", rule: null, level: null }, assessment: null, assignment: null },
    { code: "R4", title_es: "Registro comprobado", title_en: null, selection_basis: null, proposal: { decision: "undecided", rule: null, level: null },
      assessment: { applicability: "applies", implementation: "implemented", regularly_reviewed: true, justification: "", performed_by: "Ana", performed_on: "2026-11-20", evidence_statement_ids: [], notes: "", recorded_by: "u", recorded_at: "2026-11-21T10:00:00Z" }, assignment: null },
  ],
};
const unassessed = { ...framework, snapshot: null };
const render = (role: "admin" | "member" = "admin") =>
  renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" role={role} />);

it("leads with the self-assessment and shows each requirement's decision or proposal", async () => {
  stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, register] }); render();
  expect(await screen.findByRole("heading", { name: "Autoevaluación de tu organización" })).toBeTruthy();
  expect(screen.getByText("1 de 4 medidas evaluadas")).toBeTruthy();
  const row = (code: string) => Array.from(document.querySelectorAll("details.requirement-row")).find((r) => r.querySelector(".requirement-code")?.textContent === code)!;
  expect(within(row("R1") as HTMLElement).getByText(/Pendiente/).textContent).toContain("Aplica");
  expect(within(row("R4") as HTMLElement).getByText("Implantada")).toBeTruthy();
  // Without a recorded assessment the "Sin evaluar" status is noise; the register replaces it.
  expect(within(row("R1") as HTMLElement).queryByText("Sin evaluar")).toBeNull();
  expect(screen.queryByRole("button", { name: "Actualizar resultados" })).toBeNull();
});

it("shows the pack's readable labels for scope terms but stores the official values", async () => {
  const labelled = { ...register, term_labels: [
    { term: "tier", es: "Categoría sintética", en: "Synthetic tier" },
    { term: "HIGH", es: "Alta", en: "High (HIGH)" },
  ] };
  const requests = stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, labelled], [`POST ${base}/scope`]: [201, { axis_values: {}, decided_by: "u", decided_at: "2026-11-22T10:00:00Z" }] }); render();
  const tier = await screen.findByLabelText("Categoría sintética") as HTMLSelectElement;
  expect([...tier.options].map((o) => o.textContent)).toEqual(["LOW", "MID", "Alta"]);
  fireEvent.change(tier, { target: { value: "HIGH" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar alcance" }));
  const post = await vi.waitFor(() => { const r = requests.find((q) => q.method === "POST"); if (!r) throw new Error("no post"); return r; });
  expect((await post.json()).axis_values.tier).toBe("HIGH");
});

it("records the scope from the pack's declared levels", async () => {
  const requests = stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, register], [`POST ${base}/scope`]: [201, { axis_values: {}, decided_by: "u", decided_at: "2026-11-22T10:00:00Z" }] }); render();
  fireEvent.change(await screen.findByLabelText("tier"), { target: { value: "HIGH" } });
  fireEvent.change(screen.getByLabelText("I"), { target: { value: "M" } });
  fireEvent.click(screen.getByRole("button", { name: "Guardar alcance" }));
  await vi.waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
  const post = requests.find((r) => r.method === "POST")!;
  expect(await post.json()).toEqual({ axis_values: { tier: "HIGH", level: { C: "L", I: "M" } } });
});

const profile = { key: "small_it", title_es: "Perfil sintético IT", title_en: "Synthetic IT profile", summary_es: "Resumen propio del perfil.", summary_en: "Own profile summary.",
  refs: [{ guide: "Guía sintética", edition: "2026-11", section: "4", page: 8 }], reviewed_by: null, reviewed_on: null };

it("offers the pack's profiles as a scope option and stores the profile key (issue 227)", async () => {
  const requests = stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, { ...register, profiles: [profile] }], [`POST ${base}/scope`]: [201, { axis_values: {}, decided_by: "u", decided_at: "2026-11-22T10:00:00Z" }] }); render();
  const select = await screen.findByLabelText("Perfil de cumplimiento");
  fireEvent.change(select, { target: { value: "small_it" } });
  expect(screen.getByText("Resumen propio del perfil.")).toBeTruthy();
  expect(screen.getByText(/Fuentes: Guía sintética \(noviembre de 2026\), apartado 4, pág\. 8\./).textContent).toContain("pendiente de revisión cualificada");
  fireEvent.click(screen.getByRole("button", { name: "Guardar alcance" }));
  await vi.waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
  expect(await requests.find((r) => r.method === "POST")!.json()).toEqual({ axis_values: { tier: "LOW", level: { C: "L", I: "L" }, profile: "small_it" } });
});

it("cites the profile and its criteria in a proposal that comes from a profile", async () => {
  const source = profile.refs[0]!;
  const items = [{ ...register.items[0]!, proposal: { decision: "not_applicable" as const, rule: "n.a.", level: "small_it", source, criterion: { ...source, section: "5.8", page: 13 } } }];
  stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, { ...register, profiles: [profile], items }] }); render();
  await screen.findByRole("heading", { name: "Autoevaluación de tu organización" });
  const row = Array.from(document.querySelectorAll("details.requirement-row")).find((r) => r.querySelector(".requirement-code")?.textContent === "R1") as HTMLDetailsElement;
  row.open = true;
  const text = Array.from(row.querySelectorAll("p")).map((p) => p.textContent ?? "").find((t) => t.startsWith("Propuesta según el perfil adoptado"));
  expect(text).toContain("No aplica (n.a.; Guía sintética (noviembre de 2026), apartado 4, pág. 8)");
  expect(text).toContain("La guía da criterios propios para esta medida: Guía sintética (noviembre de 2026), apartado 5.8, pág. 13.");
});

const ref = { guide: "Guía sintética", edition: "2025-06", section: "3.1", page: 9 };
const guide = { axis: "level", category_axis: "tier", category_by_level: { L: "LOW", M: "MID", H: "HIGH" }, reviewed_by: null, reviewed_on: null,
  steps: [{ asset: "information" as const, key: "C", es: "¿Qué daño si se revela?", en: "What harm if disclosed?", ref },
    { asset: "information" as const, key: "I", es: "¿Qué daño si se altera?", en: "What harm if altered?", ref: { ...ref, section: "3.2" } }],
  notes: [{ es: "Primero la información.", en: "Information first.", ref: { ...ref, section: "1.2", page: 5 } }] };

it("values assets dimension by dimension and fills the scope with the highest levels (issue 225)", async () => {
  const requests = stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, { ...register, scope_guide: guide }], [`POST ${base}/scope`]: [201, { axis_values: {}, decided_by: "u", decided_at: "2026-11-22T10:00:00Z" }] }); render();
  fireEvent.click(await screen.findByText("Valorar el sistema paso a paso"));
  expect(screen.getByText(/Primero la información\./).textContent).toContain("Guía sintética (junio de 2025), apartado 1.2, pág. 5");
  fireEvent.click(screen.getByRole("button", { name: "Añadir un tipo de información" }));
  fireEvent.click(screen.getByRole("button", { name: "Añadir un tipo de información" }));
  const first = screen.getByRole("group", { name: "Información 1" });
  fireEvent.change(within(first).getByLabelText("¿Qué daño si se revela?"), { target: { value: "M" } });
  const second = screen.getByRole("group", { name: "Información 2" });
  fireEvent.change(within(second).getByLabelText("¿Qué daño si se revela?"), { target: { value: "L" } });
  fireEvent.change(within(second).getByLabelText("¿Qué daño si se altera?"), { target: { value: "H" } });
  expect(screen.getByText("Resultado: C M · I H. Categoría: HIGH.").getAttribute("role")).toBe("status");
  fireEvent.click(screen.getByRole("button", { name: "Usar estos niveles" }));
  fireEvent.click(screen.getByRole("button", { name: "Guardar alcance" }));
  await vi.waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
  expect(await requests.find((r) => r.method === "POST")!.json()).toEqual({ axis_values: { tier: "HIGH", level: { C: "M", I: "H" } } });
});

it("requires a justification when the decision differs from the proposal", async () => {
  const requests = stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, register], [`POST ${base}/register/R1`]: [201, register.items[3]!.assessment] }); render();
  await screen.findByRole("heading", { name: "Autoevaluación de tu organización" });
  const row = Array.from(document.querySelectorAll("details.requirement-row")).find((r) => r.querySelector(".requirement-code")?.textContent === "R1") as HTMLDetailsElement;
  row.open = true;
  fireEvent.click(within(row).getByRole("button", { name: "Evaluar esta medida" }));
  fireEvent.click(within(row).getByRole("radio", { name: "No aplica" }));
  const justification = within(row).getByLabelText("Justificación (obligatoria)") as HTMLTextAreaElement;
  expect(justification.required).toBe(true);
  fireEvent.change(justification, { target: { value: "El sistema no presta ese servicio." } });
  fireEvent.click(within(row).getByRole("button", { name: "Guardar" }));
  await vi.waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
  const body = await requests.find((r) => r.method === "POST")!.json();
  expect(body).toMatchObject({ applicability: "not_applicable", justification: "El sistema no presta ese servicio." });
});

it("lets members read the register but not edit it", async () => {
  stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, register] }); render("member");
  await screen.findByRole("heading", { name: "Autoevaluación de tu organización" });
  expect(screen.queryByRole("button", { name: "Guardar alcance" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Evaluar esta medida" })).toBeNull();
  expect(screen.getByText("Una persona administradora debe definir el alcance.")).toBeTruthy();
});

it("links the statement of applicability export and says it is not a certification", async () => {
  stubApi({ [`GET ${base}`]: [200, unassessed], [`GET ${base}/register`]: [200, register] }); render();
  const csv = await screen.findByRole("link", { name: "Descargar CSV" });
  expect(csv.getAttribute("href")).toBe(`${base}/applicability.csv?lang=es`);
  expect(screen.getByText(/No es una certificación/)).toBeTruthy();
});

it("titles each group with the pack's official heading, keeping the code", async () => {
  const dotted = { ...unassessed, requirements: unassessed.requirements.map((r) => ({ ...r, code: `R.${r.code}` })) };
  stubApi({ [`GET ${base}`]: [200, dotted], [`GET ${base}/register`]: [200, { ...register, items: register.items.map((i) => ({ ...i, code: `R.${i.code}` })) }] });
  renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" role="admin" />);
  const group = await screen.findByRole("region", { name: "Requisitos sintéticos" });
  expect(within(group).getByText("R")).toBeTruthy();
});

it("orders groups as the pack declares its headings, not alphabetically", async () => {
  const codes = ["b.1", "a.1"];
  const detailRows = { ...unassessed, requirements: codes.map((code, i) => ({ ...unassessed.requirements[i]!, code })) };
  const items = codes.map((code, i) => ({ ...register.items[i]!, code }));
  stubApi({ [`GET ${base}`]: [200, detailRows], [`GET ${base}/register`]: [200, { ...register, items, groups_es: [{ prefix: "b", title: "Primero" }, { prefix: "a", title: "Segundo" }] }] });
  renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" role="admin" />);
  await screen.findByRole("region", { name: "Primero" });
  const names = Array.from(document.querySelectorAll(".requirement-group")).map((g) => g.getAttribute("aria-label"));
  expect(names).toEqual(["Primero", "Segundo"]);
});

it("groups by code prefix and counts only recorded decisions", () => {
  expect(groupByPrefix([{ code: "a.1" }, { code: "a.2" }, { code: "b.c.1" }, { code: "x" }]).map(([p, g]) => [p, g.length]))
    .toEqual([["a", 2], ["b.c", 1], ["x", 1]]);
  expect(registerProgress(register.items)).toEqual({ total: 4, assessed: 1, applies: 1, notApplicable: 0, implemented: 1, partial: 0 });
});

it("orders assessed frameworks, then those with requirements, then empty templates", () => {
  const empty = { ...overview.frameworks[3]!, key: "empty", name: "Empty", requirements: 0, snapshot: null };
  const content = { ...overview.frameworks[3]!, key: "content", name: "Content", requirements: 9, snapshot: null };
  renderWithProviders(<FrameworkLedger orgId="primary" frameworks={[empty, content, overview.frameworks[0]!]} />);
  const names = Array.from(document.querySelectorAll(".framework-row strong")).map((n) => n.textContent);
  expect(names).toEqual(["Synthetic Alpha", "Content"]);
  // Templates without requirements fold away under one disclosure (readiness-cockpit spec).
  const fold = screen.getByText("1 marco en preparación, aún sin requisitos").closest("details")!;
  expect(within(fold).getByRole("link", { name: "Empty" }).getAttribute("href")).toContain("framework=empty");
});

it("orders frameworks in progress by their self-assessment, most advanced first", () => {
  const ledger = (key: string, name: string) => ({ ...overview.frameworks[3]!, key, name, requirements: 10, snapshot: null });
  const ready = (key: string, assessed: number) => ({
    key, name: key, total: 10, assessed, implemented: assessed, partial: 0, not_implemented: 0, not_applicable: 0,
    has_axes: false, scope_defined: false, review_on: null, overdue: 0, unowned_open: 0, open_by_owner: {}, last_assessed_at: null,
  });
  renderWithProviders(<FrameworkLedger orgId="primary" frameworks={[ledger("a", "Untouched"), ledger("b", "Started"), ledger("c", "Advanced")]}
    readiness={[ready("a", 0), ready("b", 2), ready("c", 7)]} />);
  const names = Array.from(document.querySelectorAll(".framework-row strong")).map((n) => n.textContent);
  expect(names).toEqual(["Advanced", "Started", "Untouched"]);
  expect(screen.getByText("7 / 10")).toBeTruthy();
  expect(screen.queryAllByText("Sin evaluar")).toHaveLength(1); // only the untouched one
});

it("points first steps at the framework with the most requirements", async () => {
  stubApi({ [`GET ${base}/register`]: [200, register] });
  renderWithProviders(<FirstSteps orgId="primary" frameworks={overview.frameworks} />);
  expect(await screen.findByRole("heading", { name: "Primeros pasos" })).toBeTruthy();
  expect(await screen.findByText("Evalúa las medidas (1 de 4)")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Continuar con Synthetic Alpha" }).getAttribute("href")).toContain("framework=synthetic_alpha");
});

it("shows catalog links by readable name, keeping the full address", () => {
  expect(referenceLabel(new URL("https://www.example.test/buscar/act.php?id=DOC-1#ai-2"))).toBe("example.test · DOC-1 · ai-2");
  expect(referenceLabel(new URL("https://example.test/guides/how-to-review.html"))).toBe("example.test · how-to-review");
});
