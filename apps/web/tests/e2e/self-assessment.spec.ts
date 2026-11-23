import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { framework } from "../fixtures/framework";
import { overview } from "../fixtures/overview";

/** Synthetic register (workspace-ux spec), never a real normative pack. */
const register = {
  framework_key: "synthetic_alpha", framework_version: "2", catalog_version: "synthetic-2",
  axes: { tier: { keys: [], levels: ["LOW", "MID", "HIGH"] } }, groups_es: [{ prefix: "R", title: "Requisitos sintéticos" }], term_labels: [],
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

  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/register/history", (route) => route.fulfill({ json: [
    { day: "2026-11-20", assessed: 1, implemented: 0, not_applicable: 0 },
    { day: "2026-11-21", assessed: 2, implemented: 1, not_applicable: 0 },
  ] }));
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
  await expect(page.getByText(/Synthetic Alpha: 6 de 10 medidas evaluadas, 4 implantadas\./)).toBeVisible();
  const now = page.getByRole("region", { name: "Ahora" });
  await expect(now.getByRole("link", { name: "2 medidas con fecha límite vencida en Synthetic Alpha" })).toHaveAttribute("href", `/app/framework?org=${org}&framework=synthetic_alpha`);
  await expect(page.getByText("6 de 10 evaluadas · 4 implantadas · 1 en parte · 1 sin implantar · 0 no aplican")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tu trabajo" })).toBeVisible();
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${width}`).toBe(true);
    await expectAccessible(page, `cockpit ${width}`);
  }
});
