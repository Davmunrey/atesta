import { type Page, expect, test } from "@playwright/test";
import { expectPolished } from "./polish";

/**
 * UI polish (ui-polish spec, #238 #239 #240): every console page with real records, at a phone and
 * a laptop width, light and dark. No axe violation of any impact, nothing scrolls sideways (inside
 * table regions too), no interface text under 13 px, standalone targets 44 px on a phone.
 */
async function seed(page: Page) {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`polish-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización de pulido");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización de pulido");
  const org = new URL(page.url()).searchParams.get("org")!;
  const o = `/api/v1/orgs/${org}`;
  const call = async (path: string, data?: unknown) => {
    const response = await page.request.post(path, { data, headers: { Origin: "http://localhost:3000" } });
    expect(response.ok(), `${path} ${response.status()}`).toBe(true);
    return response.status() === 204 ? null : response.json();
  };
  const today = new Date().toISOString().slice(0, 10);
  const policy = await call(`${o}/policies`, { title: "Política de seguridad de la información", location_url: "https://example.com/p.pdf", review_months: 12 });
  await call(`${o}/policies/${policy.id}/approvals`, { version: "2.0", approver_name: "Comité de dirección", approved_on: today });
  await call(`${o}/policies`, { title: "Política de uso aceptable", location_url: "https://example.com/u.pdf", review_months: 12 });
  const review = await call(`${o}/access-reviews`, { title: "Administradores de Microsoft 365", system: "Microsoft 365", accounts: [
    { account: "administradora.global.de.la.organizacion@example.test", detail: "Global admin" }, { account: "becario@example.test", detail: "" }] });
  await call(`${o}/access-reviews/${review.id}/decisions`, { entry_id: review.entries[0].id, decision: "keep", note: "" });
  await call(`${o}/training-campaigns`, { title: "Concienciación sobre phishing", material_url: "https://example.com/t", closes_on: new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10) });
  const incident = await call(`${o}/incidents`, { title: "Correo de phishing con enlace pulsado", aware_at: new Date(Date.now() - 3_600_000).toISOString(), significant: false, personal_data: true });
  await call(`${o}/incidents/${incident.id}/updates`, { kind: "note", note: "Contraseña cambiada y sesiones revocadas." });
  await call(`${o}/api-tokens`, { name: "Copias nocturnas", expires_in_days: 90 });
  return { org, review: review.id as string, incident: incident.id as string };
}

test("every console page is polished at 375 and 1280 px, light and dark", async ({ page }) => {
  test.setTimeout(240_000);
  const csp: string[] = [];
  page.on("console", (m) => { if (m.text().includes("Content Security Policy")) csp.push(m.text()); });
  const { org, review, incident } = await seed(page);
  const q = `org=${org}`;
  const pages = [
    "/app", `/app/org?${q}`, `/app/my-work?${q}`, `/app/frameworks?${q}`, `/app/report?${q}`,
    `/app/access-reviews?${q}`, `/app/access-review?${q}&id=${review}`, `/app/policies?${q}`, `/app/training-campaigns?${q}`,
    `/app/incidents?${q}`, `/app/incident?${q}&id=${incident}`, `/app/members?${q}`, `/app/invitations?${q}`,
    `/app/activity?${q}`, `/app/integrations?${q}`, `/app/settings?${q}`,
  ];
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    for (const width of [375, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      for (const path of pages) {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expect(page.locator("[aria-busy=true], main [role=status]:text-matches('Cargando')")).toHaveCount(0);
        await expectPolished(page, `${path} ${width} ${colorScheme}`);
      }
    }
  }
  expect(csp).toEqual([]);
});

test("activity reads as sentences for management, never as codes or ids", async ({ page }) => {
  const { org } = await seed(page);
  await page.goto(`/app/activity?org=${org}`);
  const table = page.getByRole("region", { name: "Últimas acciones" });
  await expect(table.getByText("Creó un token de integración")).toBeVisible();
  // The action column: a label, then only readable identifiers (framework keys, requirement codes).
  const what = await table.locator("tbody td:nth-child(3)").allTextContents();
  expect(what.length).toBeGreaterThan(5);
  expect(what.filter((text) => /^[a-z_]+\.[a-z_]+|[0-9a-f]{8}-[0-9a-f]{4}-/.test(text))).toEqual([]);
});
