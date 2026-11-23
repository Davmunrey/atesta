import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { settled } from "./polish";

test("an API token authenticates ingestion until it is revoked", async ({ page, request }) => {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`tokens-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización con integraciones");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización con integraciones");
  await page.getByRole("link", { name: "Integraciones" }).first().click();
  await page.getByLabel("Nombre").fill("GitHub Actions");
  await page.getByRole("button", { name: "Crear el token" }).click();
  await expect(page.getByText("Elige al menos un permiso.")).toBeVisible(); // no scope by default
  await page.getByRole("checkbox", { name: "Registrar evidencias" }).check();
  await page.getByRole("button", { name: "Crear el token" }).click();
  const token = await page.getByLabel("Token de API").inputValue();
  expect(token).toMatch(/^atesta_[\w-]{40,}$/);
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `integrations ${width}`).toBe(true);
    await settled(page);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), `integrations ${width}`).toEqual([]);
  }

  const ingest = (bearer: string) => request.post("/api/v1/ingest/evidence", {
    headers: { Authorization: `Bearer ${bearer}` },
    data: { control: "ctl.not_in_this_catalog", title: "Restore test", statement: "Restore passed.", source: "e2e" },
  });
  const accepted = await ingest(token); // the token is accepted; this empty catalog has no such control
  expect((await accepted.json()).detail.code).toBe("evidence.control_not_found");
  expect((await ingest(`atesta_${"x".repeat(43)}`)).status()).toBe(401);

  await page.getByRole("button", { name: "Revocar el token GitHub Actions" }).click();
  await expect(page.getByText(/^Revocado el /)).toBeVisible();
  const revoked = await ingest(token);
  expect([revoked.status(), (await revoked.json()).detail.code]).toEqual([401, "identity.api_token_invalid"]);
});
