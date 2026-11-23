import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { settled } from "./polish";

/** Assistant (assistant spec, #357): keyboard only, cited cards, no answer, Esc, axe. */

async function expectAccessible(page: Page, where: string) {
  await settled(page);
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(violations.flatMap((v) => v.nodes.map((node) => `${v.id}: ${node.target.join(" ")}: ${node.failureSummary}`)), where).toEqual([]);
}

/** Opens the assistant with the keyboard and asks a question; focus lands in the search field. */
async function ask(page: Page, query: string) {
  const field = page.getByRole("searchbox", { name: "Busca en el catálogo" });
  if (!(await field.isVisible())) {
    await page.getByRole("button", { name: "Asistente" }).focus();
    await page.keyboard.press("Enter");
  }
  await expect(field).toBeFocused();
  await field.fill(query);
  await page.keyboard.press("Enter");
}

async function expectCitedCards(page: Page) {
  const cards = page.getByRole("dialog").getByRole("article");
  await expect(cards.first()).toBeVisible();
  for (const card of await cards.all()) await expect(card.locator("footer")).toContainText(/Fuente: .{6,}/);
}

test("landing assistant: lazy index, cited answers, no answer, Esc returns focus, axe at 375 and 1280", async ({ page }) => {
  const reports: string[] = [];
  page.on("console", (message) => { if (message.text().includes("Content Security Policy")) reports.push(message.text()); });
  const indexRequests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/assistant/")) indexRequests.push(request.url()); });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await settled(page);
  expect(indexRequests, "the index loads on first open, not with the page").toEqual([]);

  await ask(page, "op.acc.6");
  const dialog = page.getByRole("dialog", { name: "Asistente del catálogo" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("status")).toHaveText("2 respuestas");
  await expectCitedCards(page);
  await expect(dialog.getByRole("article").first().getByRole("link", { name: "Texto oficial" })).toHaveAttribute("href", /^https:\/\/www\.boe\.es\//);
  expect(new Set(indexRequests.map((url) => new URL(url).origin))).toEqual(new Set([new URL(page.url()).origin]));
  await expectAccessible(page, "landing assistant, 1280");

  await ask(page, "receta de paella valenciana");
  await expect(dialog.getByRole("status")).toHaveText("Sin respuesta en el catálogo para esta búsqueda.");
  await expect(dialog.getByRole("link", { name: /@/ })).toHaveAttribute("href", /^mailto:/);

  await dialog.getByRole("button", { name: "¿Qué plazos tengo ante un incidente?" }).click();
  await dialog.getByLabel(/Incidente significativo/).check();
  await expect(dialog.getByText("24 horas", { exact: true })).toBeVisible();
  await expectCitedCards(page);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Asistente" })).toBeFocused();

  // Reopening keeps the open flow; focus lands on "Volver", which leads back to the search.
  await page.setViewportSize({ width: 375, height: 800 });
  await page.keyboard.press("Enter");
  await expect(dialog.getByRole("button", { name: "Volver" })).toBeFocused();
  await page.keyboard.press("Enter");
  await ask(page, "copias de seguridad");
  await expectCitedCards(page);
  const box = await dialog.boundingBox();
  expect(box?.width).toBeLessThanOrEqual(375);
  await expectAccessible(page, "landing assistant, 375");
  await dialog.getByRole("button", { name: "Cerrar" }).click();
  await expect(dialog).toBeHidden();
  expect(reports).toEqual([]);
});

test("app assistant: links answers to the organization's measure; axe light and dark", async ({ browser }) => {
  const page = await (await browser.newContext({ locale: "es-ES" })).newPage();
  const run = Date.now().toString(36);
  await page.goto("/");
  await page.getByRole("link", { name: "Entrar" }).click();
  await page.waitForURL(/localhost:9000/);
  await page.fill("input[name=email]", `assistant-${run}@example.com`);
  await page.fill("input[name=code]", "123456");
  await page.click("button");
  await page.getByLabel("Nombre de la organización").fill(`Asistente ${run}`);
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { name: `Asistente ${run}` })).toBeVisible();
  const org = new URL(page.url()).searchParams.get("org");
  expect(org).toBeTruthy();

  for (const [scheme, width] of [["light", 1280], ["dark", 1280], ["dark", 375]] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.setViewportSize({ width, height: 900 });
    await ask(page, "op.acc.6");
    const dialog = page.getByRole("dialog", { name: "Asistente del catálogo" });
    await expectCitedCards(page);
    await expect(dialog.getByRole("link", { name: "Ver en tu organización" }).first()).toHaveAttribute("href", `/app/framework?org=${org}&framework=ens_rd311_2022#req-op.acc.6`);
    await expectAccessible(page, `app assistant, ${scheme}, ${width}`);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  }
});
