import { expect, test } from "@playwright/test";
import { dossier } from "./fixtures";
import { expectPolished } from "./polish";

/**
 * Public pages (ui-polish spec, #301): the public side meets the console's bar at a phone and a
 * laptop width, under light and dark emulation. Public pages are light only (landing-legal spec,
 * L4), so dark emulation must still render the light theme. Each page shares one header.
 */
const PAGES = ["/", "/producto", "/ens", "/seguridad", "/consultoras", "/cookies", "/aviso-legal", "/privacidad", "/invite", "/training", "/training#token=not-a-real-token", "/no-such-page"];

test("every public page shares one frame and is polished at 375 and 1280 px, light and dark", async ({ page }) => {
  test.setTimeout(300_000);
  const csp: string[] = [];
  page.on("console", (m) => { if (m.text().includes("Content Security Policy")) csp.push(m.text()); });
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [375, 1280, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const path of PAGES) {
        const where = `${path} ${width} ${colorScheme}`;
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 }), where).toHaveCount(1);
        await expect(page.locator("[role=status]:text-matches('Cargando')"), where).toHaveCount(0);
        await expect(page.getByRole("link", { name: "Volver al inicio de Atesta" }), where).toBeVisible();
        await expect(page.locator("main#content"), where).toHaveCount(1);
        const theme = await page.evaluate(() => {
          const surface = document.querySelector(".public-surface")!;
          return { scheme: getComputedStyle(surface).colorScheme, background: getComputedStyle(surface).backgroundColor };
        });
        expect(theme, where).toEqual({ scheme: "light", background: "rgb(244, 241, 234)" });
        await expectPolished(page, where);
      }
    }
  }
  expect(csp).toEqual([]);
});

test("a malformed training link reads as an invalid link, not a form error", async ({ page }) => {
  await page.goto("/training#token=not-a-real-token");
  await expect(page.getByRole("heading", { level: 1, name: "Formación no disponible" })).toBeVisible();
  await expect(page.locator("main").getByRole("alert")).toHaveText("Este enlace de formación no es válido. Pide uno nuevo a quien te lo envió.");
});

test("the dossier print view is polished at 375 and 1280 px", async ({ page }) => {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`public-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización impresa");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización impresa");
  const org = new URL(page.url()).searchParams.get("org")!;
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/dossier", (route) => route.fulfill({ json: dossier }));
  await page.goto(`/app/dossier?org=${org}&framework=synthetic_alpha`);
  await expect(page.getByRole("heading", { name: "Resumen para dirección" })).toBeVisible();
  await page.emulateMedia({ media: "print" });
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expectPolished(page, `dossier print ${width}`);
  }
});

test("the header menus work by keyboard and Escape returns focus (A3)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/docs/api");
  const producto = page.getByRole("button", { name: "Producto" });
  await producto.focus();
  await page.keyboard.press("Enter");
  await expect(producto).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("link", { name: /Autoevaluación/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(producto).toHaveAttribute("aria-expanded", "false");
  await expect(producto).toBeFocused();
});

test("the header steps aside on scroll down and returns on scroll up, never under reduced motion (A3)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  const header = page.locator(".public-site-header");
  // Scroll in steps until the listener (attached after hydration) has seen the direction.
  await expect.poll(async () => { await page.mouse.wheel(0, 400); await page.waitForTimeout(150); return header.getAttribute("data-hidden"); }, { timeout: 10_000 }).toBe("true");
  await expect.poll(async () => { await page.mouse.wheel(0, -200); await page.waitForTimeout(150); return header.getAttribute("data-hidden"); }, { timeout: 10_000 }).toBe("false");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, 400); await page.waitForTimeout(150); }
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(800);
  await expect(header).toHaveAttribute("data-hidden", "false");
});
