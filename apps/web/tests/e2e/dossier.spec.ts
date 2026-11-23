import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const dossier = {
  framework_key: "synthetic_alpha", framework_name: "Synthetic framework", framework_version: "1", catalog_version: "a".repeat(64),
  generated_at: "2026-11-23T12:00:00Z", statement: "Not a certification", signer: { name: null, role: null, date: null, signature: null },
  summary: {
    counts: { key: "synthetic_alpha", name: "Synthetic", total: 3, assessed: 1, implemented: 1, partial: 0, not_implemented: 0, not_applicable: 0,
      has_axes: false, scope_defined: false, review_on: null, overdue: 0, unowned_open: 0, open_by_owner: {}, last_assessed_at: null },
    review: null,
    routines: { policies_due: 0, policies_unapproved: 1, access_reviews_overdue: 0, trainings_unclosed: 0, incident_clocks_overdue: 0 },
  },
  applicability: [{ code: "m.cat", title_es: "Medida sintética con un título bastante largo para comprobar el ajuste", decision: "applies", decided_by_person: true,
    rule: null, level: null, justification: "Aplica a todos los sistemas del alcance declarado por la organización.", implementation: "implemented" }],
  requirements: [{ code: "m.cat", title_es: "Medida sintética", title_en: null, source: "https://example.test", decision: "applies", implementation: "implemented", justification: "",
    controls: [{ key: "ctl.paper", title_es: "Política", title_en: "Policy", manual: true, observed_status: "manual", review: null,
      evidence: [{ title: "Política de seguridad", statement: "Aprobada por el comité.", reference_url: "https://intranet.example.test/politicas/seguridad-de-la-informacion-v2.pdf",
        collected_at: "2026-11-22T08:00:00Z", source_type: "user" }] }] }],
  routines: { policies: [], access_reviews: [], trainings: [], incidents: [] },
};

test("the auditor dossier reads well on a phone and a laptop", async ({ page }) => {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`dossier-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Organización del dossier");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Organización del dossier");
  const org = new URL(page.url()).searchParams.get("org")!;
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha/dossier", (route) => route.fulfill({ json: dossier }));
  await page.goto(`/app/dossier?org=${org}&framework=synthetic_alpha`);
  await expect(page.getByRole("heading", { name: "Resumen para dirección" })).toBeVisible();
  await expect(page.getByText("1 política sin aprobar")).toBeVisible();
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `dossier ${width}`).toBe(true);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), `dossier ${width}`).toEqual([]);
  }
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".sidenav")).toBeHidden();
  await expect(page.getByRole("button", { name: "Imprimir o guardar en PDF" })).toBeHidden();
});
