import { expect, test } from "@playwright/test";
import { everyView, signIn } from "./staff";

/** Screens 4 and 5 (#489): the real operator API checks the plan and the billing formats. */
test("billing staff change a plan and correct billing details the API refused", async ({ page }) => {
  await signIn(page, "billing@atesta.test", "/?q=Organizaci%C3%B3n%20de%20prueba%2007");
  await page.getByRole("link", { name: "Organización de prueba 07" }).click();
  await page.getByRole("link", { name: "Cambiar el plan" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Cambiar el plan" })).toBeVisible();
  await page.getByLabel("Plan", { exact: true }).selectOption("starter");
  const preview = page.getByRole("region", { name: "Qué cambia" });
  await expect(preview.getByText("sin límite → 1 conexión")).toBeVisible();
  await page.getByLabel("Centro de confianza").check();
  await page.getByLabel("Motivo").fill("Contrato firmado el 25 de noviembre");
  await everyView(page, "plan editor");
  await page.getByRole("button", { name: "Guardar el plan" }).click();
  const plan = page.getByRole("region", { name: "Plan" });
  await expect(plan.getByText("Starter", { exact: true })).toBeVisible();
  await expect(plan.getByText("Centro de confianza")).toBeVisible();

  await page.getByRole("region", { name: "Datos de facturación" }).getByRole("link", { name: "Editar" }).click();
  await page.getByLabel("Razón social").fill("Organización de Prueba Siete S.L.");
  await page.getByLabel("NIF").fill("123");
  await page.getByLabel("Dirección", { exact: true }).fill("Calle Real 7");
  await page.getByLabel("Código postal").fill("45001");
  await page.getByLabel("Ciudad").fill("Toledo");
  await page.getByLabel("Provincia o región").fill("Toledo");
  await page.getByLabel("País").fill("es");
  await page.getByLabel("Email de facturación").fill("facturas@prueba7.example");
  await page.getByLabel("Motivo").fill("Alta de datos de facturación");
  await page.getByRole("button", { name: "Guardar los datos de facturación" }).click();
  await expect(page.getByLabel("NIF")).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel("NIF")).toBeFocused();
  await everyView(page, "billing form with a refused field");
  await page.getByLabel("NIF").fill("B-8765432-1");
  await page.getByRole("button", { name: "Guardar los datos de facturación" }).click();
  const billing = page.getByRole("region", { name: "Datos de facturación" });
  await expect(billing.getByText("Completos")).toBeVisible();
  await expect(billing.getByText("Calle Real 7, 45001, Toledo, Toledo, ES")).toBeVisible();
});

test("support has no plan or billing actions", async ({ page }) => {
  await signIn(page, "support@atesta.test", "/?q=Cl%C3%ADnica");
  await page.getByRole("link", { name: "Clínica Norte S.L." }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Clínica Norte S.L." })).toBeVisible();
  await expect(page.getByRole("link", { name: "Cambiar el plan" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Editar" })).toHaveCount(0);
});
