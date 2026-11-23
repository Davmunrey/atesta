import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { settled } from "./polish";
import { overview } from "../fixtures/overview";

async function createOrganization(page: Page) {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`dashboard-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Equipo de ejemplo para revisar resultados");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Equipo de ejemplo para revisar resultados");
}

test("dashboard reads a real empty organization and recovers after an API failure", async ({ page }) => {
  await createOrganization(page);
  await expect(page.getByText("Todavía no hay marcos publicados")).toBeVisible();
  // The empty collection panel teaches nothing; it appears once a scan or evidence exists.
  await expect(page.getByText("Aún no hay análisis registrados")).toHaveCount(0);
  // An empty organization has nothing to refresh, so no refresh button (workspace-ux spec):
  // the failure comes from a reload instead.
  await expect(page.getByRole("button", { name: "Actualizar resultados" })).toHaveCount(0);
  await page.route("**/api/v1/orgs/*/overview", (route) => route.fulfill({ status: 503, json: { detail: { code: "auth.provider_unavailable" } } }));
  await page.reload();
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await page.unroute("**/api/v1/orgs/*/overview");
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByText("Todavía no hay marcos publicados")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Secciones de la organización" }).getByRole("link", { name: "Miembros", exact: true })).toBeVisible();
});

test("recorded-result design supports filters, keyboard disclosure, both locales and responsive themes", async ({ page }) => {
  const csp: string[] = [];
  page.on("console", (message) => { if (message.text().includes("Content Security Policy")) csp.push(message.text()); });
  // Nine frameworks: past the eight a glance covers, so the search box is offered.
  const many = { ...overview, frameworks: [...overview.frameworks, ...Array.from({ length: 5 }, (_, i) => ({ ...overview.frameworks[3]!, key: `synthetic_extra_${i}`, name: `Synthetic Extra ${i}` }))] };
  await page.route("**/api/v1/orgs/*/overview", (route) => route.fulfill({ json: many }));
  await createOrganization(page);
  await expect(page.locator(".evidence-count")).toHaveCSS("font-size", "32px");
  const row = page.locator("details").filter({ hasText: "Synthetic Alpha" });
  await expect(row).toHaveJSProperty("open", true);
  await row.locator("summary").press("Enter");
  await expect(row).toHaveJSProperty("open", false);
  await row.locator("summary").press("Enter");
  await expect(row).toHaveJSProperty("open", true);
  await expect(page.getByText("synthetic-1", { exact: true }).first()).toBeVisible();
  await page.getByRole("searchbox").fill("unmatched");
  await expect(page.getByText("Ningún marco coincide con la búsqueda")).toBeVisible();
  await page.getByRole("button", { name: "Limpiar búsqueda" }).click();
  for (const locale of ["es", "en"] as const) {
    if (locale === "en") await page.getByRole("button", { name: "English" }).click();
    await expect(page.getByRole("heading", { name: locale === "es" ? "Marcos" : "Frameworks", exact: true })).toBeVisible();
    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      for (const width of [375, 768, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate(() => document.fonts.ready);
        // A media override may be acknowledged before inherited theme colors settle.
        const dark = colorScheme === "dark";
        await expect(page.locator("body")).toHaveCSS("background-color", dark ? "rgb(23, 23, 21)" : "rgb(244, 241, 234)");
        await expect(row.locator("summary strong")).toHaveCSS("color", dark ? "rgb(244, 241, 234)" : "rgb(20, 20, 20)");
        await expect(page.getByRole("contentinfo").getByRole("link", { name: /Cookies/ })).toHaveCSS("color", dark ? "rgb(192, 186, 174)" : "rgb(85, 81, 74)");
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await settled(page);
        const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
        expect(violations.filter((v) => v.impact === "serious" || v.impact === "critical")
          .map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`), `${locale}/${colorScheme}/${width}`).toEqual([]);
      }
    }
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "Frameworks", exact: true })).toBeVisible();
  expect(csp).toEqual([]);
});
