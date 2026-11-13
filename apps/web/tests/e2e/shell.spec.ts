import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

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
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  const serious = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(serious.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`), screen).toEqual([]);
}

function cspReports(page: Page): string[] {
  const reports: string[] = [];
  page.on("console", (message) => {
    if (message.text().includes("Content Security Policy")) reports.push(message.text());
  });
  return reports;
}

test("sign in, create an org, invite, accept as a second user, change role, remove", async ({ browser }) => {
  const ownerPage = await (await browser.newContext()).newPage();
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

  await ownerPage.getByRole("link", { name: "Invitaciones" }).click();
  await ownerPage.getByLabel("Correo electrónico").fill(guest);
  await ownerPage.getByRole("button", { name: "Invitar" }).click();
  const link = await ownerPage.getByLabel("Enlace de invitación").inputValue();
  await expect(ownerPage.getByText(/solo se muestra una vez/)).toBeVisible();
  await expectAccessible(ownerPage, "invitations");

  const guestPage = await (await browser.newContext()).newPage();
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
  await expect(guestPage.getByText("Tu rol: Miembro")).toBeVisible();
  expect(await guestPage.evaluate(() => sessionStorage.getItem("atesta_invite:v1"))).toBeNull();

  await ownerPage.goto(orgHome);
  await ownerPage.getByRole("link", { name: "Miembros" }).click();
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

test("security headers on every page; no referrer from /invite", async ({ request }) => {
  for (const path of ["/", "/app", "/invite", "/no-such-page"]) {
    const response = await request.get(path);
    const headers = response.headers();
    expect(headers["content-security-policy"], path).toContain("frame-ancestors 'none'");
    expect(headers["content-security-policy"], path).not.toContain("unsafe-inline");
    expect(headers["x-content-type-options"], path).toBe("nosniff");
    expect(headers["strict-transport-security"], path).toContain("max-age=");
    expect(headers["referrer-policy"], path).toBe(path === "/invite" ? "no-referrer" : "same-origin");
  }
  expect((await request.get("/no-such-page")).status()).toBe(404);
});
