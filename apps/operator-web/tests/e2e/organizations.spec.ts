import { expect, test } from "@playwright/test";
import { everyView, signIn } from "./staff";

/** Screens 2 and 3 (#488) against the seeded organizations (prepare_e2e_db.py --operator). */
test("staff find an organization by name, filter, page through the list and open it", async ({ page }) => {
  await signIn(page, "billing@atesta.test");
  const results = page.getByRole("region", { name: "Organizaciones encontradas" });
  await expect(results.getByRole("row")).toHaveCount(51);
  await expect(page.getByRole("navigation", { name: "Páginas" }).getByRole("status")).toHaveText("1–50 de 53");
  await everyView(page, "organization list");
  await page.getByRole("button", { name: "Siguiente" }).click();
  await expect(page).toHaveURL(/\?page=2$/);
  await expect(results.getByRole("row")).toHaveCount(4);
  await page.getByLabel("Estado").selectOption("suspended");
  await expect(results.getByRole("link")).toHaveText(["Clínica Norte S.L."]);
  await page.getByLabel("Estado").selectOption("");
  await page.getByLabel("Nombre o identificador").fill("zzz");
  await page.getByRole("button", { name: "Buscar" }).click();
  await expect(page.getByText("Ninguna organización coincide con la búsqueda o los filtros.")).toBeVisible();
  await everyView(page, "organization list empty");
  await page.getByRole("button", { name: "Borrar la búsqueda y los filtros" }).click();
  await page.getByLabel("Nombre o identificador").fill("clínica");
  await page.getByRole("button", { name: "Buscar" }).click();
  await results.getByRole("link", { name: "Clínica Norte S.L." }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Clínica Norte S.L." })).toBeVisible();
  await expect(page.getByRole("region", { name: "Datos de facturación" }).getByText("B12345678")).toBeVisible();
  await expect(page.getByRole("region", { name: "Estado" }).getByText("Pago pendiente")).toBeVisible();
  await everyView(page, "organization detail (billing)");
});

test("support reads the same organization without its tax ID, address or billing email", async ({ page }) => {
  await signIn(page, "support@atesta.test", "/?q=Cl%C3%ADnica");
  await page.getByRole("link", { name: "Clínica Norte S.L." }).click();
  const billing = page.getByRole("region", { name: "Datos de facturación" });
  await expect(billing.getByText("Clínica Norte Sociedad Limitada")).toBeVisible();
  await expect(billing.getByText("B12345678")).toHaveCount(0);
  await expect(billing.getByText("NIF")).toHaveCount(0);
  await everyView(page, "organization detail (support)");
});
