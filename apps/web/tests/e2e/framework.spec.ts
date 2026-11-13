import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { framework } from "../fixtures/framework";
import { overview } from "../fixtures/overview";

async function createOrganization(page: Page) {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`framework-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Equipo de ejemplo para revisar requisitos");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Equipo de ejemplo para revisar requisitos");
  return new URL(page.url()).searchParams.get("org")!;
}

test("framework route handles a real absent catalog and recovers from read failures", async ({ page }) => {
  const org = await createOrganization(page);
  await page.goto(`/app/framework?org=${org}&framework=absent`);
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Este marco no está disponible");
  await page.getByRole("link", { name: "Volver al resumen" }).click();
  await expect(page.getByText("Todavía no hay marcos publicados")).toBeVisible();
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ status: 503, json: {} }));
  await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha`);
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await page.unroute("**/api/v1/orgs/*/frameworks/synthetic_alpha");
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: framework }));
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Synthetic Alpha" })).toBeVisible();
});

test("framework register supports navigation, guidance, filters, locales and responsive themes", async ({ page }) => {
  const csp: string[] = [];
  page.on("console", (message) => { if (message.text().includes("Content Security Policy")) csp.push(message.text()); });
  await page.route("**/api/v1/orgs/*/overview", (route) => route.fulfill({ json: overview }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: framework }));
  await createOrganization(page);
  await page.getByRole("link", { name: "Ver requisitos y configuración" }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Synthetic Alpha");
  await expect(page.getByRole("navigation", { name: "Secciones de la organización" }).getByRole("link", { name: "Resumen" })).toHaveAttribute("aria-current", "page");
  const row = page.locator("details.requirement-row").filter({ hasText: "R1" });
  await row.locator("summary").press("Enter");
  await expect(row).toHaveJSProperty("open", false);
  await row.locator("summary").press("Enter");
  await expect(row).toHaveJSProperty("open", true);
  await expect(row.getByRole("link", { name: "https://example.test/guide" })).toHaveAttribute("rel", "noopener noreferrer");
  await expect(row.getByRole("link", { name: "javascript:alert(1)" })).toHaveCount(0);
  await page.getByRole("button", { name: "No cumple 1", exact: true }).click();
  await expect(page.locator("details.requirement-row")).toHaveCount(1);
  await page.getByRole("searchbox").fill("absent");
  await page.getByRole("button", { name: "Limpiar filtros" }).click();
  for (const locale of ["es", "en"] as const) {
    if (locale === "en") await page.getByRole("button", { name: "English" }).click();
    await expect(page.getByRole("heading", { name: locale === "es" ? "Requisitos y configuración" : "Requirements and configuration", exact: true })).toBeVisible();
    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      for (const width of [375, 768, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate(() => document.fonts.ready);
        const dark = colorScheme === "dark";
        await expect(page.locator("body")).toHaveCSS("background-color", dark ? "rgb(23, 23, 21)" : "rgb(244, 241, 234)");
        await expect(row.locator("summary strong")).toHaveCSS("color", dark ? "rgb(244, 241, 234)" : "rgb(20, 20, 20)");
        await expect(page.getByRole("contentinfo").getByRole("link")).toHaveCSS("color", dark ? "rgb(192, 186, 174)" : "rgb(85, 81, 74)");
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
        expect(violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`), `${locale}/${colorScheme}/${width}`).toEqual([]);
      }
    }
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "Requirements and configuration", exact: true })).toBeVisible();
  expect(csp).toEqual([]);
});
