import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { settled } from "@atesta/ui/e2e-polish";

async function createOrganization(page: Page) {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`routines-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización con rutinas");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización con rutinas");
  return new URL(page.url()).searchParams.get("org")!;
}

async function expectSound(page: Page, where: string) {
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${where} ${width}`).toBe(true);
    await settled(page);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), `${where} ${width}`).toEqual([]);
  }
}

test("an access review is decided and closed, and a policy approved, through the real API", async ({ page }) => {
  const org = await createOrganization(page);
  await page.goto(`/app/access-reviews?org=${org}`);
  await page.getByLabel("Nombre de la revisión").fill("Administradores Q4");
  await page.getByLabel("Sistema revisado").fill("Microsoft 365");
  await page.getByLabel("Cuentas", { exact: true }).fill("ana@example.test, Global admin\nbecario@example.test");
  await expect(page.getByText("2 cuentas listas")).toBeVisible();
  await expectSound(page, "access reviews");
  await page.getByRole("button", { name: "Empezar la revisión" }).click();
  await page.getByRole("link", { name: "Administradores Q4" }).click();
  await expect(page.getByRole("button", { name: "Cerrar y registrar" })).toBeDisabled();
  await page.getByRole("group", { name: "Decisión para ana@example.test" }).getByRole("button", { name: "Mantener" }).click();
  await page.getByRole("group", { name: "Decisión para becario@example.test" }).getByRole("button", { name: "Retirar" }).click();
  await expect(page.getByText("2 de 2 cuentas decididas")).toBeVisible();
  await expectSound(page, "access review");
  await page.getByRole("button", { name: "Cerrar y registrar" }).click();
  await expect(page.getByText(/^Cerrada el /)).toBeVisible();

  await page.goto(`/app/policies?org=${org}`);
  await page.getByLabel("Nombre de la política").fill("Política de seguridad");
  await page.getByLabel("Enlace al documento (https)").fill("https://example.test/politica.pdf");
  await page.getByRole("button", { name: "Añadir política" }).click();
  await expect(page.getByRole("region", { name: "Registro de políticas" }).getByText("Sin aprobar")).toBeVisible();
  await page.getByRole("button", { name: "Registrar aprobación" }).click();
  await page.getByLabel("Versión", { exact: true }).fill("1.0");
  await page.getByLabel("Aprobada por").fill("Comité de seguridad");
  await page.getByRole("button", { name: "Registrar", exact: true }).click();
  await expect(page.getByText(/^Versión 1.0, aprobada por Comité de seguridad/)).toBeVisible();
  await expectSound(page, "policies");
});

test("a training link is confirmed without an account, and an incident is recorded and closed", async ({ page, browser }) => {
  const org = await createOrganization(page);
  await page.goto(`/app/training-campaigns?org=${org}`);
  await page.getByLabel("Nombre de la formación").fill("Phishing 2026");
  await page.getByLabel("Enlace al material (https)").fill("https://example.test/phishing.pdf");
  await page.getByLabel("Fecha de cierre").fill(new Date(Date.now() + 14 * 86_400_000).toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Crear y obtener el enlace" }).click();
  const link = await page.getByLabel("Enlace de la formación").inputValue();
  expect(link).toMatch(/\/training#token=[\w-]{20,}$/);
  await expectSound(page, "training");

  const guest = await (await browser.newContext()).newPage();
  await guest.goto(link.replace(/^https?:\/\/[^/]+/, ""));
  await expect(guest.getByRole("heading", { name: "Phishing 2026" })).toBeVisible();
  expect(new URL(guest.url()).hash).toBe("");
  await expectSound(guest, "training link");
  await guest.getByLabel("Nombre y apellidos").fill("Ana Pérez");
  await guest.getByLabel("Correo electrónico").fill("ana@example.test");
  await guest.getByLabel("He leído el material").check();
  await guest.getByRole("button", { name: "Confirmar" }).click();
  await expect(guest.getByText("Gracias. Tu confirmación ha quedado registrada.")).toBeVisible();
  await guest.context().close();

  await page.reload();
  await page.getByRole("link", { name: "Phishing 2026" }).click();
  await expect(page.getByRole("cell", { name: "ana@example.test" })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar y registrar" }).click();
  await expect(page.getByText(/^Cerrada el /)).toBeVisible();

  await page.goto(`/app/incidents?org=${org}`);
  await page.getByLabel("Descripción breve").fill("Correo de phishing con enlace pulsado");
  await page.getByLabel("Afecta a datos personales").check();
  await expectSound(page, "incidents");
  await page.getByRole("button", { name: "Registrar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Correo de phishing con enlace pulsado");
  await page.getByLabel("Nueva anotación").fill("Contraseña cambiada y sesiones revocadas.");
  await page.getByRole("button", { name: "Añadir la anotación" }).click();
  await expect(page.getByText("Contraseña cambiada y sesiones revocadas.")).toBeVisible();
  await expectSound(page, "incident");
  // No pack here runs a clock, so closing needs no confirmation (console-unification spec; unit-tested with one).
  await page.getByRole("button", { name: "Cerrar el incidente" }).click();
  await expect(page.getByText("Incidente cerrado. La evidencia se ha registrado en el control de gestión de incidentes.")).toBeVisible();
});
