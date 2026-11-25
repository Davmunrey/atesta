import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { settled } from "@atesta/ui/e2e-polish";
import { framework, requirementGuidance } from "../fixtures/framework";
import { overview } from "../fixtures/overview";

/** Synthetic register (workspace-ux spec), never a real normative pack. */
const register = {
  framework_key: "synthetic_alpha", framework_version: "2", catalog_version: "synthetic-2",
  axes: { tier: { keys: [], levels: ["LOW", "MID", "HIGH"] } }, groups_es: [{ prefix: "R", title: "Requisitos sintéticos" }], term_labels: [], profiles: [], scope_guide: null,
  scope: null as null | { axis_values: Record<string, string>; decided_by: string; decided_at: string }, review: null,
  items: framework.requirements.filter((r) => r.in_current_catalog).map((r) => ({
    code: `R.${r.code}`, title_es: r.title_es!, title_en: null, selection_basis: "tier · Todas",
    proposal: { decision: "applies", rule: "+ R1", level: "MID" }, assessment: null as null | Record<string, unknown>, assignment: null,
  })),
};
const detail = { ...framework, snapshot: null, requirements: framework.requirements.filter((r) => r.in_current_catalog).map((r) => ({ ...r, code: `R.${r.code}` })) };

async function createOrganization(page: Page) {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`register-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización de ejemplo");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización de ejemplo");
  return new URL(page.url()).searchParams.get("org")!;
}

async function expectAccessible(page: Page, where: string) {
  await settled(page);
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), where).toEqual([]);
}

test("an admin scopes, assesses and exports the self-assessment, accessibly at every width", async ({ page }) => {
  const csp: string[] = [];
  page.on("console", (m) => { if (m.text().includes("Content Security Policy")) csp.push(m.text()); });
  const org = await createOrganization(page);
  // One organization: its name, no switcher; the account sits behind one button.
  await expect(page.getByLabel("Organización", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/@example\.test/)).toBeHidden();
  await page.getByRole("button", { name: "Cuenta" }).click();
  await expect(page.getByText(/@example\.test/)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText(/@example\.test/)).toBeHidden();

  const state = { ...register };
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: detail }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/register", (route) => route.fulfill({ json: state }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/scope", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ axis_values: { tier: "HIGH" } });
    state.scope = { axis_values: { tier: "HIGH" }, decided_by: "u", decided_at: "2026-11-22T10:00:00Z" };
    return route.fulfill({ status: 201, json: state.scope });
  });
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/register/R.R1", async (route) => {
    const body = route.request().postDataJSON();
    expect(body).toMatchObject({ applicability: "not_applicable", justification: "No prestamos ese servicio." });
    const saved = { ...body, recorded_by: "u", recorded_at: "2026-11-22T10:05:00Z" };
    state.items = state.items.map((i) => i.code === "R.R1" ? { ...i, assessment: saved } : i);
    return route.fulfill({ status: 201, json: saved });
  });

  // Seven days of change: the trend chart earns its place (console-unification spec).
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/register/history", (route) => route.fulfill({ json:
    Array.from({ length: 7 }, (_, i) => ({ day: `2026-11-${String(15 + i).padStart(2, "0")}`, assessed: i + 1, implemented: i, not_applicable: 0 })) }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/trend", (route) => route.fulfill({ json: [] }));
  await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha`);
  await expect(page.getByRole("heading", { name: "Autoevaluación de tu organización" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Medidas implantadas a lo largo del tiempo/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Requisitos sintéticos" })).toBeVisible();
  await expectAccessible(page, "workspace before scope");

  await page.getByLabel("tier").selectOption("HIGH");
  await page.getByRole("button", { name: "Guardar alcance" }).click();
  await expect(page.getByText(/Alcance registrado/)).toBeVisible();

  const row = page.locator("details.requirement-row").filter({ hasText: "R.R1" });
  await row.locator("summary").first().click();
  await row.getByRole("button", { name: "Evaluar esta medida" }).click();
  await row.getByRole("radio", { name: "No aplica" }).check();
  const justification = row.getByLabel("Justificación (obligatoria)");
  await expect(justification).toHaveAttribute("required", "");
  await justification.fill("No prestamos ese servicio.");
  await row.getByRole("button", { name: "Guardar" }).click();
  await expect(row.locator("summary").first().getByText("No aplica")).toBeVisible();
  await expect(page.getByText("1 de 4 medidas evaluadas")).toBeVisible();
  await expect(page.getByRole("link", { name: "Descargar CSV" })).toHaveAttribute("href", `/api/v1/orgs/${org}/frameworks/synthetic_alpha/applicability.csv?lang=es`);

  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    for (const width of [375, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${colorScheme} ${width}`).toBe(true);
      await expectAccessible(page, `${colorScheme} ${width}`);
    }
  }
  expect(csp).toEqual([]);
});

test("an agent's proposal reads as one block a person decides, at every width", async ({ page }) => {
  const org = await createOrganization(page);
  const proposal = {
    id: "p1", applicability: "applies", implementation: "partially_implemented", regularly_reviewed: false,
    justification: "", performed_by: "Responsable de sistemas", performed_on: null, evidence_statement_ids: [],
    notes: "Política publicada en la intranet; falta la revisión anual del comité de seguridad de la información.",
    rationale: "El acta del comité de 2026-11-02 aprueba la política, pero no consta ninguna revisión posterior. ".repeat(3),
    proposed_at: "2026-11-22T10:00:00Z", token_name: "Agente de Claude del equipo de sistemas", token_prefix: "atesta_abcde",
  };
  const state = { ...register, items: register.items.map((i, n) => n === 0 ? { ...i, pending_proposal: proposal } : i) };
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: detail }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/register", (route) => route.fulfill({ json: state }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/register/history", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/trend", (route) => route.fulfill({ json: [] }));
  await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha`);
  const row = page.locator("details.requirement-row").filter({ hasText: "R.R1" });
  await row.locator("summary").first().click();
  const notice = row.getByRole("region", { name: "Propuesta de un agente" });
  await expect(notice).toBeVisible();
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    for (const width of [375, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${colorScheme} ${width}`).toBe(true);
      expect(await notice.evaluate((el) => getComputedStyle(el).display), `${width}`).toBe("grid");
      const box = (await notice.boundingBox())!;
      for (const name of ["Confirmar la propuesta", "Rechazar la propuesta"]) {
        const button = (await notice.getByRole("button", { name }).boundingBox())!;
        expect(button.x >= box.x && button.x + button.width <= box.x + box.width + 1, `${name} ${width}`).toBe(true);
      }
      await expectAccessible(page, `proposal ${colorScheme} ${width}`);
    }
  }
});

test("an admin reads the organization's real activity, accessibly", async ({ page }) => {
  const org = await createOrganization(page);
  await page.getByRole("navigation", { name: "Secciones de la organización" }).getByRole("link", { name: "Actividad", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Actividad", level: 1 })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Creó la organización" })).toBeVisible();
  await page.getByRole("button", { name: "Últimos 90 días" }).click();
  await expect(page.getByRole("button", { name: "Últimos 90 días" })).toHaveAttribute("aria-pressed", "true");
  expect(new URL(page.url()).searchParams.get("org")).toBe(org);
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}`).toBe(true);
    await expectAccessible(page, `activity ${width}`);
  }
});

test("the dashboard cockpit says where we stand, what needs attention and who does what, accessibly", async ({ page }) => {
  const org = await createOrganization(page);
  const readiness = [{
    key: "synthetic_alpha", name: "Synthetic Alpha", total: 10, assessed: 6, implemented: 4, partial: 1, not_implemented: 1,
    not_applicable: 0, has_axes: true, scope_defined: true, review_on: null, overdue: 2, unowned_open: 3,
    open_by_owner: {}, last_assessed_at: "2026-11-20T10:00:00Z",
  }];
  await page.route("**/api/v1/orgs/*/overview", (route) => route.fulfill({ json: overview }));
  await page.route("**/api/v1/orgs/*/readiness", (route) => route.fulfill({ json: readiness }));
  await page.reload();
  const now = page.getByRole("region", { name: "Ahora" });
  await expect(now.getByRole("link", { name: "2 medidas con fecha límite vencida en Synthetic Alpha" })).toHaveAttribute("href", `/app/framework?org=${org}&framework=synthetic_alpha`);
  // The task list is the first region after the header; progress is stated once, on the framework line.
  expect(await page.locator("main section.panel").first().evaluate((el) => el.classList.contains("attention"))).toBe(true);
  await expect(page.getByRole("region", { name: "Marcos" }).getByRole("listitem").filter({ hasText: "Synthetic Alpha" })).toHaveText("Synthetic Alpha6 de 10 medidas evaluadas · 4 implantadas");
  for (const width of [375, 390, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}`).toBe(true);
    await expectAccessible(page, `cockpit ${width}`);
  }
});

test("a measure reads as the shared sheet: the record beside the law, stacked on a phone (issue 426)", async ({ page }) => {
  const org = await createOrganization(page);
  const guided = { ...detail, requirements: detail.requirements.map((r, n) => n === 0 ? { ...r, guidance: { ...requirementGuidance, official_text_es: "Primer párrafo.\n\nSegundo párrafo." } } : r) };
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: guided }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/register", (route) => route.fulfill({ json: register }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/register/history", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/trend", (route) => route.fulfill({ json: [] }));
  await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha#req-R.R1`);
  const row = page.locator("details.requirement-row.measure-sheet").filter({ hasText: "R.R1" });
  await expect(row).toHaveAttribute("open", "");
  await row.locator("summary", { hasText: "Leer texto oficial" }).click();
  const law = row.locator(".measure-sheet-law");
  await expect(law.locator("blockquote.official-text")).toHaveAttribute("lang", "es");
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    for (const [width, sideBySide] of [[375, false], [1280, true]] as const) {
      await page.setViewportSize({ width, height: 900 });
      // Both boxes from one settled frame: two separate reads can straddle a style change (#456).
      await settled(page);
      const { a, b } = await row.evaluate((sheet) => {
        const box = (part: string) => sheet.querySelector(part)!.getBoundingClientRect().toJSON() as DOMRect;
        return { a: box(".measure-sheet-record"), b: box(".measure-sheet-law") };
      });
      expect(Math.abs(a.y - b.y) < 1 && b.x > a.x + a.width, `${colorScheme} ${width} side by side`).toBe(sideBySide);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${colorScheme} ${width}`).toBe(true);
      await expectAccessible(page, `measure sheet ${colorScheme} ${width}`);
    }
  }
});
