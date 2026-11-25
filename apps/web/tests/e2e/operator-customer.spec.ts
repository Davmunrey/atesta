import { type Page, expect, test } from "@playwright/test";
import { expectPolished } from "@atesta/ui/e2e-polish";

/**
 * What customers see of the operator (operator-portal spec): the suspended page for an owner and a
 * member, the read-only notice after the trial, the billing details and the Atesta team in
 * Activity. The real API and database serve everything; the operator's writes (build step 4) are
 * not built yet, so their effect is patched into the responses that carry it.
 */
async function signUp(page: Page): Promise<string> {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`operator-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización suspendida S.L.");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización suspendida S.L.");
  return new URL(page.url()).searchParams.get("org")!;
}

/** Rewrites the organization's membership in /me, as the API answers once the operator acts. */
async function patchMe(page: Page, patch: Record<string, unknown>) {
  await page.route("**/api/v1/me", async (route) => {
    const body = await (await route.fetch()).json();
    body.memberships = body.memberships.map((m: Record<string, unknown>) => ({ ...m, ...patch }));
    await route.fulfill({ json: body });
  });
}

const suspended = { suspended: true, suspended_at: "2026-11-20T09:00:00Z" };
const billing = {
  legal_name: "Organización suspendida S.L.", tax_id: "B00000000", address_line1: "Calle Mayor 1", address_line2: null,
  postal_code: "28001", city: "Madrid", region: "Madrid", country: "ES", contact_email: "facturas@example.test",
  complete: true, updated_at: "2026-11-20T09:00:00Z",
};

async function everyView(page: Page, where: string) {
  for (const [width, scheme] of [[1280, "light"], [375, "light"], [1280, "dark"], [375, "dark"]] as const) {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ colorScheme: scheme });
    await expectPolished(page, `${where} ${width} ${scheme}`);
  }
}

test("a suspended organization shows one page: the owner keeps export, closure and billing", async ({ page }) => {
  const org = await signUp(page);
  await patchMe(page, { ...suspended, suspension_reason: "non_payment" });
  await page.route("**/api/v1/orgs/*/billing-profile", (route) => route.fulfill({ json: billing }));
  await page.goto(`/app/frameworks?org=${org}`);
  await expect(page.getByRole("heading", { level: 1, name: "Organización suspendida" })).toBeVisible();
  await expect(page.getByText("Motivo: pago pendiente. Para reactivarla, escribe a hello@atesta.cloud.")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Secciones de la organización" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Datos de facturación" }).getByText("Calle Mayor 1")).toBeVisible();
  await everyView(page, "suspended owner");
  await page.getByRole("link", { name: "Cerrar la organización" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /Ajustes/ })).toBeVisible();
  await expect(page.getByLabel("Idioma de los avisos por email")).toHaveCount(0);
});

test("a suspended organization's member reads the generic text", async ({ page }) => {
  const org = await signUp(page);
  await patchMe(page, { ...suspended, role: "member", suspension_reason: null });
  await page.goto(`/app/org?org=${org}`);
  await expect(page.getByText("Para saber más, habla con la persona propietaria de la organización.")).toBeVisible();
  await expect(page.getByText(/Motivo/)).toHaveCount(0);
  await everyView(page, "suspended member");
});

test("after the trial the console says it is read-only, and Activity names the Atesta team", async ({ page }) => {
  const org = await signUp(page);
  await page.route("**/api/v1/orgs/*/trial", (route) => route.fulfill({ json: { ends_at: "2026-11-10T09:00:00Z", ended: true } }));
  await page.route("**/api/v1/orgs/*/activity*", async (route) => {
    const body = await (await route.fetch()).json();
    body.events.unshift({ occurred_at: new Date().toISOString(), actor_email: null, actor_kind: "atesta", action: "operator.plan_changed", target_type: "organization", target_id: org });
    await route.fulfill({ json: body });
  });
  await page.goto(`/app/activity?org=${org}`);
  await expect(page.getByText(/La organización es de solo lectura/)).toBeVisible();
  const row = page.getByRole("row", { name: /Cambió el plan/ });
  await expect(row.getByText("Equipo de Atesta")).toBeVisible();
  await everyView(page, "trial ended, activity");
});
