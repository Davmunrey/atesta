import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { settled } from "./polish";
import { dossier } from "./fixtures";

test("the auditor dossier reads well on a phone and a laptop", async ({ page }) => {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`dossier-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización del dossier");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización del dossier");
  const org = new URL(page.url()).searchParams.get("org")!;
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/dossier", (route) => route.fulfill({ json: dossier }));
  await page.goto(`/app/dossier?org=${org}&framework=synthetic_alpha`);
  await expect(page.getByRole("heading", { name: "Resumen para dirección" })).toBeVisible();
  await expect(page.getByText("1 política sin aprobar")).toBeVisible();
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `dossier ${width}`).toBe(true);
    await settled(page);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), `dossier ${width}`).toEqual([]);
  }
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".sidenav")).toBeHidden();
  await expect(page.getByRole("button", { name: "Imprimir o guardar en PDF" })).toBeHidden();
});
