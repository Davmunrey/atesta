import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { settled } from "@atesta/ui/e2e-polish";

test("a person with two organizations sees them as a portfolio", async ({ page }) => {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`portfolio-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  for (const name of ["Cliente Uno S.L.", "Cliente Dos S.L."]) {
    if (name === "Cliente Dos S.L.") await page.goto("/app/new");
    await page.getByLabel("Nombre de la organización").fill(name);
    await page.getByRole("button", { name: "Crear organización" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(name);
  }
  // Issue 228: the table comes from one request, not two per organization.
  const calls: string[] = [];
  page.on("request", (request) => {
    const { pathname } = new URL(request.url());
    if (pathname === "/api/v1/portfolio" || /\/(readiness|routines\/due)$/.test(pathname)) calls.push(pathname);
  });
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Tus organizaciones" })).toBeVisible();
  await expect(page.getByRole("list", { name: "Resumen de la cartera" })).toContainText("2 organizaciones");
  const table = page.getByRole("table");
  await expect(table.getByRole("link", { name: "Cliente Uno S.L." })).toBeVisible();
  await expect(table.getByRole("link", { name: "Cliente Dos S.L." })).toBeVisible();
  await expect(table.getByText("Cargando…")).toHaveCount(0);
  await expect(table.getByText("Sin empezar")).toHaveCount(2); // read by the API, each in its own context
  expect(calls).toEqual(["/api/v1/portfolio"]);
  for (const [width, colorScheme] of [[375, "light"], [1280, "light"], [1280, "dark"]] as const) {
    await page.emulateMedia({ colorScheme });
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `portfolio ${width} ${colorScheme}`).toBe(true);
    await settled(page);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), `portfolio ${width} ${colorScheme}`).toEqual([]);
  }
  await page.emulateMedia({ colorScheme: "light" });
  await table.getByRole("link", { name: "Cliente Dos S.L." }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Cliente Dos S.L.");
});
