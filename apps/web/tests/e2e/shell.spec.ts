import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { settled } from "./polish";

const run = Date.now().toString(36);
const owner = `owner-${run}@example.com`;
const guest = `guest-${run}@example.com`;
const org = `Acme ${run}`;

async function signIn(page: Page, email: string) {
  await page.waitForURL(/localhost:9000/);
  await page.fill("input[name=email]", email);
  await page.fill("input[name=code]", "123456");
  await page.click("button");
}

/** WCAG 2.1 AA (web-shell spec): no serious or critical axe violations. */
async function expectAccessible(page: Page, screen: string) {
  await settled(page);
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.flatMap((v) => v.nodes.map((node) => `${v.id}: ${node.target.join(" ")}: ${node.failureSummary}`)), screen).toEqual([]);
}

function cspReports(page: Page): string[] {
  const reports: string[] = [];
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) reports.push(message.text());
  });
  return reports;
}

test("sign in, create an org, invite, accept as a second user, change role, remove", async ({ browser }) => {
  const ownerPage = await (await browser.newContext({ locale: "es-ES" })).newPage();
  const ownerCsp = cspReports(ownerPage);
  await ownerPage.goto("/");
  await expectAccessible(ownerPage, "landing");
  await ownerPage.getByRole("link", { name: "Iniciar sesión" }).click();
  await signIn(ownerPage, owner);
  await expect(ownerPage.getByLabel("Nombre de la organización")).toBeVisible();
  await expectAccessible(ownerPage, "create organization");
  await ownerPage.getByLabel("Nombre de la organización").fill(org);
  await ownerPage.getByRole("button", { name: "Crear organización" }).click();
  await expect(ownerPage.getByRole("heading", { name: org })).toBeVisible();
  const orgHome = ownerPage.url();
  await expectAccessible(ownerPage, "organization home");

  await ownerPage.getByRole("navigation", { name: "Secciones de la organización" }).getByRole("link", { name: "Invitaciones", exact: true }).click();
  await ownerPage.getByLabel("Correo electrónico").fill(guest);
  await ownerPage.getByRole("button", { name: "Invitar" }).click();
  const link = await ownerPage.getByLabel("Enlace de invitación").inputValue();
  await expect(ownerPage.getByText(/solo se muestra una vez/)).toBeVisible();
  await expectAccessible(ownerPage, "invitations");

  const guestPage = await (await browser.newContext({ locale: "es-ES" })).newPage();
  const guestCsp = cspReports(guestPage);
  // Hold /me so the page stays put while we look at the address bar and storage; once
  // released, the route just lets every /me through.
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await guestPage.route("**/api/v1/me", async (route) => {
    await held;
    await route.continue();
  });
  await guestPage.goto(link);
  await expect.poll(() => guestPage.evaluate(() => window.location.hash)).toBe("");
  const token = new URL(link).hash.slice("#token=".length);
  expect(await guestPage.evaluate(() => sessionStorage.getItem("atesta_invite:v1"))).toBe(token);
  release();
  await signIn(guestPage, guest);
  await guestPage.waitForURL("/invite");
  await expect(guestPage.getByRole("button", { name: "Aceptar invitación" })).toBeVisible();
  await expectAccessible(guestPage, "accept invitation");
  await guestPage.getByRole("button", { name: "Aceptar invitación" }).click();
  // The role is no longer repeated under the heading (workspace-ux spec); the guest lands in the
  // organization, and a member sees no invitations section.
  await expect(guestPage.getByRole("heading", { name: org })).toBeVisible();
  await expect(guestPage.getByRole("navigation", { name: "Secciones de la organización" }).getByRole("link", { name: "Invitaciones", exact: true })).toHaveCount(0);
  expect(await guestPage.evaluate(() => sessionStorage.getItem("atesta_invite:v1"))).toBeNull();

  await ownerPage.goto(orgHome);
  await ownerPage.getByRole("navigation", { name: "Secciones de la organización" }).getByRole("link", { name: "Miembros", exact: true }).click();
  const role = ownerPage.getByLabel(`Rol de ${guest}`);
  await expect(role).toHaveValue("member");
  await expectAccessible(ownerPage, "members");
  await role.selectOption("admin");
  await expect(role).toHaveValue("admin");
  await ownerPage.reload();
  await expect(ownerPage.getByLabel(`Rol de ${guest}`)).toHaveValue("admin");
  const row = ownerPage.locator("tr", { hasText: guest });
  await row.getByRole("button", { name: "Quitar" }).click();
  await row.getByRole("button", { name: "Confirmar" }).click();
  await expect(row).toHaveCount(0);

  await guestPage.reload();
  await expect(guestPage.getByText("No encontramos lo que buscas, o no tienes acceso.")).toBeVisible();
  expect([...ownerCsp, ...guestCsp]).toEqual([]);
});

test("Spanish by default, English after switching, kept after reload and sent to sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await page.getByRole("button", { name: "English" }).click();
  await page.reload();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.getByRole("link", { name: "Sign in" }).click();
  await page.waitForURL(/localhost:9000/);
  expect(new URL(page.url()).searchParams.get("lang")).toBe("en");
});

test("a first visit from an English browser opens in English; a choice then wins", async ({ browser }) => {
  const context = await browser.newContext({ locale: "en-US" });
  const page = await context.newPage();
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  await page.getByRole("button", { name: "Español" }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await context.close();
});

test("the policy blocks an injected inline script", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      (window as unknown as { violated: string }).violated = event.effectiveDirective;
    });
    const script = document.createElement("script");
    script.textContent = "window.pwned = true";
    document.body.append(script);
  });
  await expect.poll(() => page.evaluate(() => (window as unknown as { violated?: string }).violated)).toBe("script-src-elem");
  expect(await page.evaluate(() => (window as unknown as { pwned?: boolean }).pwned)).toBeUndefined();
});

test("security headers on every page; no referrer from /invite or /training", async ({ request }) => {
  for (const path of ["/", "/app", "/invite", "/training", "/no-such-page"]) {
    const response = await request.get(path);
    const headers = response.headers();
    expect(headers["content-security-policy"], path).toContain("frame-ancestors 'none'");
    expect(headers["content-security-policy"], path).not.toContain("unsafe-inline");
    expect(headers["x-content-type-options"], path).toBe("nosniff");
    expect(headers["strict-transport-security"], path).toContain("max-age=");
    expect(headers["referrer-policy"], path).toBe(["/invite", "/training"].includes(path) ? "no-referrer" : "same-origin");
  }
  expect((await request.get("/no-such-page")).status()).toBe(404);
});

test("organization navigation, local fonts and long content work across sizes and themes", async ({ page }) => {
  test.setTimeout(120_000);
  const fonts: string[] = [];
  page.on("request", (request) => { if (request.resourceType() === "font") fonts.push(request.url()); });
  const reports = cspReports(page);
  await page.goto("/");
  await page.getByRole("link", { name: "Iniciar sesión" }).click();
  await signIn(page, `layout-${run}@example.test`);
  const longName = "Synthetic accessibility organization " + "x".repeat(100);
  await page.getByLabel("Nombre de la organización").fill(longName);
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { name: longName })).toBeVisible();
  const home = page.url();
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    for (const width of [375, 768, 1280]) {
      await page.setViewportSize({ width, height: 850 });
      for (const name of ["Resumen", "Miembros", "Invitaciones"]) {
        const nav = page.getByRole("navigation", { name: "Secciones de la organización" });
        // Below 64rem the navigation is a drawer behind the menu button (console-shell spec).
        if (width < 1024) await page.getByRole("button", { name: "Mostrar el menú" }).click();
        await nav.getByRole("link", { name, exact: true }).click();
        if (width < 1024) await page.getByRole("button", { name: "Mostrar el menú" }).click();
        await expect(nav.getByRole("link", { name, exact: true })).toHaveAttribute("aria-current", "page");
        const title = name === "Resumen" ? longName : `${name} de ${longName}`;
        await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
        // The route attribute can update before the browser applies its selected styles.
        const active = nav.getByRole("link", { name, exact: true });
        await expect(active).toHaveCSS("color", "rgb(20, 20, 20)");
        await expect(active).toHaveCSS("background-color", "rgb(255, 229, 138)");
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${name} ${width} ${colorScheme}`).toBe(true);
        await expectAccessible(page, `${name} ${width} ${colorScheme}`);
        if (width < 1024) await page.getByRole("button", { name: "Ocultar el menú" }).click();
        if (name === "Miembros") {
          const table = page.getByRole("region", { name: `Miembros de ${longName}` });
          await expect(table).toHaveAttribute("tabindex", "0");
          await table.focus();
          await expect(table).toBeFocused();
        }
      }
    }
  }
  await page.goto(home);
  await expect(page.getByRole("heading", { name: longName })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Saltar al contenido" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  const type = await page.evaluate(async () => {
    await document.fonts.ready;
    return [document.body, document.querySelector("h1")!].map((element) => {
      const family = getComputedStyle(element).fontFamily.split(",")[0]!.replaceAll('"', "").trim();
      return { family, loaded: [...document.fonts].some((font) => font.family.replaceAll('"', "") === family && font.status === "loaded") };
    });
  });
  expect(new Set(type.map(({ family }) => family)).size).toBe(2);
  expect(type.every(({ loaded }) => loaded)).toBe(true);
  expect(fonts.length).toBeGreaterThanOrEqual(2);
  expect(fonts.every((url) => new URL(url).origin === new URL(home).origin && new URL(url).pathname.endsWith(".woff2"))).toBe(true);
  expect(await page.getByRole("button", { name: "English" }).evaluate((element) => getComputedStyle(element).transitionDuration)).toBe("1e-05s");
  for (const path of ["/", "/no-such-page"]) {
    await page.goto(path);
    expect(await page.getByRole("main").evaluate((element) => getComputedStyle(element).colorScheme)).toBe("light");
  }
  expect(reports).toEqual([]);
});
