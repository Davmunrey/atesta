import { expect, test } from "@playwright/test";
import { everyView, signIn } from "./staff";

/** Portal smoke (#487): the real operator API and Postgres, the fake staff pool, axe. */
test("signed out, the portal names itself and sends staff to their own pool", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("banner").getByText("Portal de operaciones")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1, name: "Portal de operaciones" })).toBeVisible();
  await everyView(page, "sign-in");
  await page.getByRole("link", { name: "Iniciar sesión" }).click();
  await expect(page).toHaveURL(/^http:\/\/localhost:9001\/oauth2\/authorize\?.*client_id=local-operator/);
});

test("an admin signs in, sees every section, and signs out", async ({ page }) => {
  await signIn(page, "admin@atesta.test");
  const nav = page.getByRole("navigation", { name: "Secciones del portal" });
  await expect(nav.getByRole("link")).toHaveText(["Organizaciones", "Organizaciones borradas", "Equipo", "Registro de operaciones"]);
  await expect(page.getByRole("heading", { level: 1, name: "Organizaciones" })).toBeVisible();
  await everyView(page, "admin home");
  await page.getByRole("button", { name: "Cuenta" }).click();
  await expect(page.getByText("Administración", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Cerrar sesión" }).click();
  await expect(page.getByRole("link", { name: "Iniciar sesión" })).toBeVisible();
});

test("support sees only the organizations; an unknown staff account sees why it has no access", async ({ page }) => {
  await signIn(page, "support@atesta.test");
  await expect(page.getByRole("navigation", { name: "Secciones del portal" }).getByRole("link")).toHaveText(["Organizaciones"]);
  await page.context().clearCookies();
  await page.goto("/");
  await page.getByRole("link", { name: "Iniciar sesión" }).click();
  await page.locator("input[name=email]").fill("stranger@atesta.test");
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await expect(page.getByRole("heading", { level: 1, name: "Sin acceso al portal" })).toBeVisible();
  await everyView(page, "no access");
});

test("English after switching; the policy CloudFront sends refuses framing and other origins", async ({ page }) => {
  const response = await page.goto("/");
  const csp = response!.headers()["content-security-policy"]!;
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("connect-src 'self'");
  expect(csp).toMatch(/script-src 'self'(;|$)/);
  await page.getByRole("button", { name: "EN (English)" }).click();
  await expect(page.getByRole("banner").getByText("Operations portal")).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
});
