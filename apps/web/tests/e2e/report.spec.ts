import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { settled } from "./polish";

test("the monthly report reads well on a phone and a laptop, and prints clean", async ({ page }) => {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`report-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización del informe");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización del informe");
  await page.getByRole("link", { name: "Informe mensual" }).first().click();
  await expect(page.getByRole("heading", { name: /^Hecho en / })).toBeVisible();
  await expect(page.getByText("Es el estado actual, no el del final del mes.")).toBeVisible();
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `report ${width}`).toBe(true);
    await settled(page);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), `report ${width}`).toEqual([]);
  }
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("button", { name: "Imprimir o guardar en PDF" })).toBeHidden();
});
