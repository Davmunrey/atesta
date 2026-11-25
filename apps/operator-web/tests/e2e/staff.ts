import { type Page, expect } from "@playwright/test";
import { expectPolished } from "@atesta/ui/e2e-polish";

/** Signs in through the fake staff pool (fake_cognito.py --staff); prepare_e2e_db.py --operator
 *  seeds admin@, second-admin@, billing@ and support@atesta.test. */
export async function signIn(page: Page, email: string, path = "/") {
  await page.goto(path);
  await page.getByRole("link", { name: "Iniciar sesión" }).click();
  await page.waitForURL(/localhost:9001/);
  await page.locator("input[name=email]").fill(email);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.waitForURL((url) => url.port === "3001" && !url.pathname.startsWith("/auth"));
  await expect(page.getByRole("button", { name: "Cuenta" })).toBeVisible();
}

/** The polish bar at the spec's sizes (1280 and 375 px, light and dark), with axe. */
export async function everyView(page: Page, where: string) {
  for (const [width, scheme] of [[1280, "light"], [375, "light"], [1280, "dark"], [375, "dark"]] as const) {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: scheme });
    await expectPolished(page, `${where} ${width} ${scheme}`);
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: "light" });
}
