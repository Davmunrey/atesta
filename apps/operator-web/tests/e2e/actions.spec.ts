import { type Page, expect, test } from "@playwright/test";
import { everyView, signIn } from "./staff";

/** Screens 6 to 8 (#490): admin actions against the real operator API and its rules. */
const NAME = "Organización de prueba 09";

async function open(page: Page, email: string) {
  await signIn(page, email, `/?q=${encodeURIComponent(NAME)}`);
  await page.getByRole("link", { name: NAME }).click();
  await expect(page.getByRole("heading", { level: 1, name: NAME })).toBeVisible();
}

async function act(page: Page, panel: string, action: string, { reason = "Prueba e2e", name = false } = {}) {
  const region = page.getByRole("region", { name: panel });
  await region.getByRole("button", { name: action }).click();
  const form = region.getByRole("form", { name: action });
  await form.getByLabel("Motivo interno").fill(reason);
  if (name) await form.getByLabel(`Escribe «${NAME}» para confirmar`).fill(NAME);
  return form;
}

test("an admin suspends and reactivates, starts the closure and requests erasure; a second admin approves it", async ({ page }) => {
  await open(page, "admin@atesta.test");
  const suspend = await act(page, "Suspensión", "Suspender la organización", { name: true });
  await suspend.getByLabel("Motivo que verá la organización").selectOption("contract_ended");
  await everyView(page, "suspend form");
  await suspend.getByRole("button", { name: "Suspender la organización" }).click();
  await expect(page.getByRole("region", { name: "Estado" }).getByText("Contrato finalizado")).toBeVisible();
  await (await act(page, "Suspensión", "Reactivar la organización")).getByRole("button", { name: "Reactivar la organización" }).click();
  await expect(page.getByRole("region", { name: "Suspensión" }).getByRole("button", { name: "Suspender la organización" })).toBeVisible();

  await (await act(page, "Exportación y cierre", "Pedir a los propietarios que exporten")).getByRole("button", { name: "Pedir a los propietarios que exporten" }).click();
  await expect(page.getByText("Hemos avisado a las personas propietarias por email.")).toBeVisible();
  await (await act(page, "Exportación y cierre", "Iniciar el cierre", { name: true })).getByRole("button", { name: "Iniciar el cierre" }).click();
  await expect(page.getByRole("region", { name: "Exportación y cierre" }).getByText(/Atesta inició el cierre/)).toBeVisible();
  await (await act(page, "Borrado", "Pedir el borrado", { name: true })).getByRole("button", { name: "Pedir el borrado" }).click();
  const erasure = page.getByRole("region", { name: "Borrado" });
  await expect(erasure.getByText("Pendiente de aprobación")).toBeVisible();
  await expect(erasure.getByText(/La pediste el/)).toBeVisible();
  await everyView(page, "erasure pending, requested by me");

  // The requester is refused (two admins exist), with the API's own message.
  await (await act(page, "Borrado", "Aprobar el borrado", { name: true })).getByRole("button", { name: "Aprobar el borrado" }).click();
  await expect(erasure.getByRole("alert")).toHaveText("Otra persona administradora debe aprobar el borrado que pediste.");

  await page.getByRole("button", { name: "Cuenta" }).click();
  await page.getByRole("link", { name: "Cerrar sesión" }).click();
  await open(page, "second-admin@atesta.test");
  await expect(erasure.getByText(/por otra persona administradora/)).toBeVisible();
  await (await act(page, "Borrado", "Aprobar el borrado", { name: true })).getByRole("button", { name: "Aprobar el borrado" }).click();
  await expect(erasure.getByText("Aprobada, a la espera de la fecha")).toBeVisible();
  await everyView(page, "erasure approved");
});
