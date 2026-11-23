import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

async function createOrganization(page: Page) {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`routines-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización con rutinas");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización con rutinas");
  return new URL(page.url()).searchParams.get("org")!;
}

async function expectSound(page: Page, where: string) {
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${where} ${width}`).toBe(true);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), `${where} ${width}`).toEqual([]);
  }
}

test("an access review is decided and closed, and a policy approved, through the real API", async ({ page }) => {
  const org = await createOrganization(page);
  await page.goto(`/app/access-reviews?org=${org}`);
  await page.getByLabel("Nombre de la revisión").fill("Administradores Q4");
  await page.getByLabel("Sistema revisado").fill("Microsoft 365");
  await page.getByLabel("Cuentas", { exact: true }).fill("ana@example.test, Global admin\nbecario@example.test");
  await expect(page.getByText("2 cuentas listas")).toBeVisible();
  await expectSound(page, "access reviews");
  await page.getByRole("button", { name: "Empezar la revisión" }).click();
  await page.getByRole("link", { name: "Administradores Q4" }).click();
  await expect(page.getByRole("button", { name: "Cerrar y registrar" })).toBeDisabled();
  await page.getByRole("group", { name: "Decisión para ana@example.test" }).getByRole("button", { name: "Mantener" }).click();
  await page.getByRole("group", { name: "Decisión para becario@example.test" }).getByRole("button", { name: "Retirar" }).click();
  await expect(page.getByText("2 de 2 cuentas decididas")).toBeVisible();
  await expectSound(page, "access review");
  await page.getByRole("button", { name: "Cerrar y registrar" }).click();
  await expect(page.getByText(/^Cerrada el /)).toBeVisible();

  await page.goto(`/app/policies?org=${org}`);
  await page.getByLabel("Nombre de la política").fill("Política de seguridad");
  await page.getByLabel("Enlace al documento (https)").fill("https://example.test/politica.pdf");
  await page.getByRole("button", { name: "Añadir política" }).click();
  await expect(page.getByText("Sin aprobar")).toBeVisible();
  await page.getByRole("button", { name: "Registrar aprobación" }).click();
  await page.getByLabel("Versión", { exact: true }).fill("1.0");
  await page.getByLabel("Aprobada por").fill("Comité de seguridad");
  await page.getByRole("button", { name: "Registrar", exact: true }).click();
  await expect(page.getByText(/^Versión 1.0, aprobada por Comité de seguridad/)).toBeVisible();
  await expectSound(page, "policies");
});
