import AxeBuilder from "@axe-core/playwright";
import { type BrowserContext, type Page, expect, test } from "@playwright/test";

async function expectLifetime(context: BrowserContext, name: string, seconds: number, httpOnly: boolean) {
  const cookie = (await context.cookies()).find((item) => item.name === name);
  expect(cookie !== undefined, `${name} exists`).toBe(true);
  // Never include cookie values in assertion output.
  expect({ secure: cookie!.secure, httpOnly: cookie!.httpOnly, sameSite: cookie!.sameSite })
    .toEqual({ secure: true, httpOnly, sameSite: "Lax" });
  const remaining = cookie!.expires - Date.now() / 1000;
  expect(remaining, `${name} remaining seconds`).toBeGreaterThan(seconds - 15);
  expect(remaining).toBeLessThanOrEqual(seconds + 1);
}

async function expectAccessible(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(violations.filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help}`)).toEqual([]);
}

test("public cookie information is reachable without creating storage or third-party requests", async ({ page, context }) => {
  const requests: string[] = [];
  const csp: string[] = [];
  page.on("request", (request) => requests.push(new URL(request.url()).origin));
  page.on("console", (message) => { if (message.text().includes("Content Security Policy")) csp.push(message.text()); });
  await page.goto("/");
  await page.getByRole("contentinfo").getByRole("link", { name: "Cookies y almacenamiento" }).click({ timeout: 5000 });
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Cookies y almacenamiento");
  expect((await context.cookies()).map(({ name }) => name)).toEqual([]);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
  expect(requests.every((origin) => origin === new URL(page.url()).origin)).toBe(true);
  expect(csp).toEqual([]);
  await expect(page.getByRole("link", { name: "Documentación de Amazon Cognito" })).toHaveAttribute("href", "https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-managed-login.html");
});

test("rendered cookie lifetimes match actual sign-in, language choice and sign-out", async ({ page, context }) => {
  await page.goto("/cookies");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Cookies y almacenamiento", { timeout: 5000 });
  const inventory = await page.locator("dl > div").evaluateAll((rows) => Object.fromEntries(rows.map((row) => [
    row.querySelector("dt")!.textContent!.trim(), Number(row.querySelector("time")!.getAttribute("datetime")!.slice(2, -1)),
  ])));
  expect(Object.keys(inventory).sort()).toEqual(["atesta_at", "atesta_auth", "atesta_locale", "atesta_rt"]);
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await expectLifetime(context, "atesta_auth", inventory.atesta_auth!, true);
  await page.locator("input[name=email]").fill(`cookies-${Date.now()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await expect(page.getByRole("heading", { name: "Crea tu organización" })).toBeVisible();
  expect((await context.cookies()).map(({ name }) => name).sort()).toEqual(["atesta_at", "atesta_rt"]);
  await expectLifetime(context, "atesta_at", inventory.atesta_at!, true);
  await expectLifetime(context, "atesta_rt", inventory.atesta_rt!, true);
  await page.getByRole("contentinfo").getByRole("link", { name: "Cookies y almacenamiento" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Cookies y almacenamiento");
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Crea tu organización" })).toBeVisible();
  await page.getByRole("button", { name: "English" }).click();
  await expectLifetime(context, "atesta_locale", inventory.atesta_locale!, false);
  await page.getByRole("link", { name: "Sign out" }).click();
  await page.waitForURL("/");
  expect((await context.cookies()).map(({ name }) => name)).toEqual(["atesta_locale"]);
});

test("the information stays readable and accessible in both locales and all viewport sizes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await page.goto("/cookies");
  for (const [locale, title] of [["es", "Cookies y almacenamiento"], ["en", "Cookies and storage"]] as const) {
    if (locale === "en") await page.getByRole("button", { name: "English" }).click();
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title, { timeout: 5000 });
    await expect(page.locator("html")).toHaveAttribute("lang", locale);
    for (const width of [375, 768, 1280]) {
      await page.setViewportSize({ width, height: 850 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(page.getByRole("main")).toHaveCSS("color-scheme", "light");
      await expectAccessible(page);
    }
    await expect(page.getByText("atesta_invite:v1", { exact: true })).toBeVisible();
    const index = page.getByRole("navigation", { name: locale === "es" ? "En esta página" : "On this page" });
    await index.getByRole("link", { name: locale === "es" ? "Tus opciones" : "Your options" }).press("Enter");
    await expect(page).toHaveURL(/#choices$/);
  }
});
