import { expect, test } from "@playwright/test";
import { everyView, signIn } from "./staff";

/** Screens 9 to 11 (#491) against the real operator API: team, operations log, erased organizations. */
test("an admin changes a role with a reason, then finds it in the operations log", async ({ page }) => {
  await signIn(page, "admin@atesta.test");
  await page.getByRole("navigation", { name: "Secciones del portal" }).getByRole("link", { name: "Equipo" }).click();
  const team = page.getByRole("region", { name: "Personas del equipo" });
  await expect(team.getByRole("row", { name: /admin@atesta.test/ }).getByText("Tú")).toBeVisible();
  await expect(team.getByRole("row", { name: /former@atesta.test/ }).getByText("Desactivado")).toBeVisible();
  await everyView(page, "team");
  await team.getByRole("row", { name: /rotating@atesta.test/ }).getByRole("button", { name: "Gestionar" }).click();
  await page.getByRole("button", { name: "Cambiar el rol de rotating@atesta.test" }).click();
  const form = page.getByRole("form", { name: "Cambiar el rol de rotating@atesta.test" });
  await form.getByLabel("Nuevo rol").selectOption("billing");
  await form.getByLabel("Motivo interno").fill("Cubre la facturación esta semana");
  await everyView(page, "team, changing a role");
  await form.getByRole("button", { name: "Cambiar el rol" }).click();
  await expect(team.getByRole("row", { name: /rotating@atesta.test/ }).getByRole("cell", { name: "Facturación" })).toBeVisible();

  await page.getByRole("link", { name: "Registro de operaciones" }).click();
  await page.getByLabel("Acción").selectOption("staff.role_changed");
  const log = page.getByRole("region", { name: "Operaciones" });
  const row = log.getByRole("row", { name: /Cambió el rol de una persona del equipo/ }).first();
  await expect(row.getByText("Cubre la facturación esta semana")).toBeVisible();
  await expect(row.getByText("admin@atesta.test")).toBeVisible();
  await everyView(page, "operations log");

  await page.getByRole("link", { name: "Organizaciones borradas" }).click();
  const receipts = page.getByRole("region", { name: "Recibos de borrado" });
  await expect(receipts.getByRole("row")).toHaveCount(2);
  await expect(receipts.getByText("4", { exact: true })).toBeVisible();
  await everyView(page, "erased organizations");
});
