import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";
import { expectPolished, settled } from "@atesta/ui/e2e-polish";
import { framework, paperEvidence, passingReview, preparationFramework, requirementGuidance, withManualControl } from "../fixtures/framework";
import { overview } from "../fixtures/overview";

async function createOrganization(page: Page) {
  await page.goto("/app");
  await page.waitForURL(/localhost:9000/);
  await page.locator("input[name=email]").fill(`framework-${crypto.randomUUID()}@example.test`);
  await page.locator("input[name=code]").fill("123456");
  await page.getByRole("button").click();
  await page.getByLabel("Nombre de la organización").fill("Equipo de ejemplo para revisar requisitos");
  await page.getByRole("button", { name: "Crear organización" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Equipo de ejemplo para revisar requisitos");
  return new URL(page.url()).searchParams.get("org")!;
}

test("evidence form supports keyboard submission and responsive themes", async ({ page }) => {
  const org = await createOrganization(page);
  const proof = { id: "synthetic-proof", kind: "attestation", title: "Synthetic policy", statement: "Synthetic evidence for browser verification.", reference_url: null, created_by: null, created_at: "2026-11-14T12:00:00Z", collected_at: "2026-11-14T12:00:00Z" };
  let saved = false;
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: withManualControl(null) }));
  await page.route("**/api/v1/orgs/*/controls/ctl.paper/evidence*", async (route) => {
    if (route.request().method() === "POST") {
      expect(route.request().postDataJSON()).toMatchObject({ title: proof.title, statement: proof.statement, reference_url: null });
      saved = true;
      return route.fulfill({ status: 201, json: proof });
    }
    return route.fulfill({ json: { total: saved ? 1 : 0, items: saved ? [proof] : [] } });
  });
  await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha`);
  const control = page.locator("article").filter({ hasText: "ctl.paper" });
  const requirement = page.locator("details.requirement-row").filter({ hasText: "ctl.paper" });
  await requirement.locator("summary").click();
  await control.getByRole("button", { name: "Ver evidencias" }).press("Enter");
  await control.getByRole("button", { name: "Registrar evidencia" }).click();
  await control.getByLabel("Nombre de la evidencia").fill(proof.title);
  await control.getByLabel("Qué demuestra").fill(proof.statement);
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    for (const width of [375, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator("body")).toHaveCSS("background-color", colorScheme === "dark" ? "rgb(23, 23, 21)" : "rgb(244, 241, 234)");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await settled(page);
      const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
    }
  }
  await control.getByRole("button", { name: "Guardar evidencia" }).click();
  await expect(control.getByText("Evidencia registrada. La revisión se decide por separado.")).toBeVisible();
  await page.reload();
  await requirement.locator("summary").click();
  await control.getByRole("button", { name: "Ver evidencias" }).click();
  await expect(control.getByText(proof.statement)).toBeVisible();
  await page.getByRole("button", { name: "English" }).click();
  if (await requirement.getAttribute("open") === null) await requirement.locator("summary").click();
  const toggle = control.getByRole("button", { name: /^(View|Hide) evidence$/ });
  if (await toggle.getAttribute("aria-expanded") === "false") await toggle.click();
  await expect(control.getByRole("button", { name: "Record evidence" })).toBeVisible();
});

test("framework route handles a real absent catalog and recovers from read failures", async ({ page }) => {
  const org = await createOrganization(page);
  await page.goto(`/app/framework?org=${org}&framework=absent`);
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Este marco no está disponible");
  await page.getByRole("navigation", { name: "Ruta" }).getByRole("link").first().click();
  await expect(page.getByText("Todavía no hay marcos publicados")).toBeVisible();
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ status: 503, json: {} }));
  await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha`);
  await expect(page.getByRole("main").getByRole("alert")).toBeVisible();
  await page.unroute("**/api/v1/orgs/*/frameworks/synthetic_alpha");
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: framework }));
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Synthetic Alpha" })).toBeVisible();
});

test("framework register supports navigation, guidance, filters, locales and responsive themes", async ({ page }) => {
  const csp: string[] = [];
  page.on("console", (message) => { if (message.text().includes("Content Security Policy")) csp.push(message.text()); });
  await page.route("**/api/v1/orgs/*/overview", (route) => route.fulfill({ json: overview }));
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: framework }));
  await createOrganization(page);
  await page.getByRole("region", { name: "Marcos" }).getByRole("link", { name: "Synthetic Alpha" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Synthetic Alpha");
  await expect(page.getByRole("navigation", { name: "Secciones de la organización" }).getByRole("link", { name: "Marcos" })).toHaveAttribute("aria-current", "page");
  const row = page.locator("details.requirement-row").filter({ hasText: "R1" });
  await row.locator("summary").press("Enter");
  await expect(row).toHaveJSProperty("open", false);
  await row.locator("summary").press("Enter");
  await expect(row).toHaveJSProperty("open", true);
  await expect(row.getByRole("link", { name: "example.test · guide" })).toHaveAttribute("rel", "noopener noreferrer");
  await expect(row.getByRole("link", { name: "javascript:alert(1)" })).toHaveCount(0);
  await page.getByRole("button", { name: "No superado 1", exact: true }).click();
  await expect(page.locator("details.requirement-row")).toHaveCount(1);
  await page.getByRole("searchbox").fill("absent");
  await page.getByRole("button", { name: "Limpiar filtros" }).click();
  for (const locale of ["es", "en"] as const) {
    if (locale === "en") await page.getByRole("button", { name: "English" }).click();
    await expect(page.getByRole("heading", { name: locale === "es" ? "Requisitos y configuración" : "Requirements and configuration", exact: true })).toBeVisible();
    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
      for (const width of [375, 768, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate(() => document.fonts.ready);
        const dark = colorScheme === "dark";
        await expect(page.locator("body")).toHaveCSS("background-color", dark ? "rgb(23, 23, 21)" : "rgb(244, 241, 234)");
        await expect(row.locator("summary strong")).toHaveCSS("color", dark ? "rgb(244, 241, 234)" : "rgb(20, 20, 20)");
        await expect(page.getByRole("contentinfo").getByRole("link", { name: /Cookies/ })).toHaveCSS("color", dark ? "rgb(192, 186, 174)" : "rgb(85, 81, 74)");
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await settled(page);
        const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
        expect(violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes.map((n) => n.failureSummary).join("; ")}`), `${locale}/${colorScheme}/${width}`).toEqual([]);
      }
    }
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "Requirements and configuration", exact: true })).toBeVisible();
  expect(csp).toEqual([]);
});

test("preparation exposes scope, missing work, official rules and configuration guides", async ({ page }) => {
  const org = await createOrganization(page);
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: {
    ...preparationFramework, requirements: [{ ...framework.requirements[0], status: "not_evaluated", guidance: requirementGuidance }],
  } }));
  await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha`);
  await expect(page.getByText(/Puntuación automática desactivada/)).toBeVisible();
  for (const label of ["Alcance y aplicabilidad", "Qué falta para evaluar", "Fuentes oficiales"]) await page.locator("summary").getByText(label, { exact: true }).click();
  await expect(page.getByText("Faltan requisitos y mapeos revisados.")).toBeVisible();
  await page.getByRole("link", { name: "1 guía de preparación" }).click();
  const control = page.locator(".preparation-control");
  await control.locator("summary").press("Enter");
  await expect(control.getByText("synthetic_access_check")).toBeVisible();
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await settled(page);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id)).toEqual([]);
  }
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.getByRole("heading", { name: "Preparation template" })).toBeVisible();
  await expect(page.getByText("Reviewed requirements and mappings are missing.")).toBeVisible();
  await expect(page.getByRole("table")).toContainText("BAJO");
  await page.locator("summary").getByText("Read full official text (Spanish)").click();
  await expect(page.locator("blockquote.official-text", { hasText: requirementGuidance.official_text_es })).toHaveAttribute("lang", "es");
});

test("an owner records a human review of a manual control, accessibly and within the CSP", async ({ page }) => {
  const csp: string[] = [];
  page.on("console", (message) => { if (message.text().includes("Content Security Policy")) csp.push(message.text()); });
  const org = await createOrganization(page);
  let reviewed = false;
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: withManualControl(reviewed ? passingReview : null) }));
  await page.route("**/api/v1/orgs/*/controls/ctl.paper/reviews", (route) => { reviewed = true; return route.fulfill({ status: 201, json: passingReview }); });
  await page.route("**/api/v1/orgs/*/controls/ctl.paper/evidence?*", (route) => route.fulfill({ json: paperEvidence }));
  await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha`);
  await page.locator("details.requirement-row").filter({ hasText: "R2" }).locator("summary").click();  // failures open first
  const card = page.locator("article.control-guide").filter({ hasText: "Plan de respuesta sintético" });
  await expect(card.getByText(/Sin revisión registrada/)).toBeVisible();
  await card.getByRole("button", { name: "Registrar revisión" }).click();
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await settled(page);
    const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => v.id), `${width}`).toEqual([]);
  }
  await card.getByRole("checkbox", { name: /Acta del comité 12/ }).check();
  await card.getByRole("radio", { name: "Implantado", exact: true }).check();
  await card.getByLabel("Justificación").fill("Acta 12 aprobada por la dirección.");
  const post = page.waitForRequest((request) => request.method() === "POST" && request.url().includes("/reviews"));
  await card.getByRole("button", { name: "Guardar revisión" }).click();
  expect((await post).postDataJSON()).toMatchObject({
    status: "pass", rationale: "Acta 12 aprobada por la dirección.", evidence_ids: [paperEvidence.items[0]!.id],
  });
  await expect(card.getByRole("status")).toContainText("Revisión registrada");
  await expect(card.getByText("Punto 3 aprobado.", { exact: false })).toBeVisible();
  await expect(card.getByRole("list", { name: "Evidencias citadas" })).toContainText("Acta del comité 12");
  expect(csp).toEqual([]);
});

test("a member uploads an evidence file, sees its malware scan and downloads it once clean", async ({ page }) => {
  const csp: string[] = [];
  page.on("console", (message) => { if (message.text().includes("Content Security Policy")) csp.push(message.text()); });
  const org = await createOrganization(page);
  const uploads = { enabled: true, max_bytes: 25 * 1024 * 1024, extensions: ["csv", "docx", "jpeg", "jpg", "pdf", "png", "txt", "xlsx"] };
  const stored = {
    id: "44444444-4444-4444-8444-444444444444", kind: "document", title: "Política de acceso", statement: null, reference_url: null,
    created_by: null, created_at: "2026-11-24T09:00:00Z", collected_at: "2026-11-24T09:00:00Z",
    file: { name: "politica-de-acceso.pdf", media_type: "application/pdf", size_bytes: 345_678, sha256: "a".repeat(64), scan_status: "pending" },
  };
  const scan = (scan_status: string) => ({ ...stored, file: { ...stored.file, scan_status } });
  let status = "pending";
  const bytes = Buffer.from("%PDF-1.7\n%synthetic policy\n%%EOF\n");
  let saved = false;
  let tampered = false;
  await page.route("**/api/v1/orgs/*/frameworks/synthetic_alpha", (route) => route.fulfill({ json: withManualControl(null) }));
  await page.route("**/api/v1/orgs/*/controls/ctl.paper/evidence*", (route) => route.fulfill({ json: { total: saved ? 1 : 0, items: saved ? [scan(status)] : [], file_uploads: uploads } }));
  await page.route("**/api/v1/orgs/*/controls/ctl.paper/evidence/files", (route) => {
    const sent = route.request().postData() ?? "";
    expect(route.request().headers()["content-type"]).toContain("multipart/form-data; boundary=");
    expect(sent).toContain('name="file"; filename="politica-de-acceso.pdf"');
    expect(sent).toContain('name="title"\r\n\r\nPolítica de acceso');
    expect(sent).toMatch(/name="submission_id"\r\n\r\n[0-9a-f-]{36}/);
    saved = true;
    return route.fulfill({ status: 201, json: stored });
  });
  await page.route("**/api/v1/orgs/*/evidence/*/file", (route) => tampered
    ? route.fulfill({ status: 409, json: { detail: { code: "evidence.file_integrity_failed" } } })
    : route.fulfill({ body: bytes, contentType: "application/pdf", headers: { "content-disposition": 'attachment; filename="politica-de-acceso.pdf"' } }));
  const control = page.locator("article").filter({ hasText: "ctl.paper" });
  const openEvidence = async () => {
    await page.goto(`/app/framework?org=${org}&framework=synthetic_alpha`);
    await page.locator("details.requirement-row").filter({ hasText: "ctl.paper" }).locator("summary").click();
    await control.getByRole("button", { name: "Ver evidencias" }).click();
  };
  await openEvidence();
  await control.getByRole("button", { name: "Subir archivo" }).press("Enter");
  await expect(control.getByLabel("Archivo")).toBeFocused();
  await expect(control.getByText("PDF, PNG, JPG, TXT, CSV, DOCX o XLSX. Hasta 25 MB.")).toBeVisible();
  await control.getByLabel("Archivo").setInputFiles({ name: "politica-de-acceso.pdf", mimeType: "application/pdf", buffer: bytes });
  await expect(control.getByLabel("Nombre de la evidencia")).toHaveValue("politica-de-acceso");
  await expect(control.getByText("Atesta analiza cada archivo en busca de malware antes de que se pueda descargar.")).toBeVisible();
  await control.getByLabel("Nombre de la evidencia").fill("Política de acceso");
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    for (const width of [375, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await expectPolished(page, `upload form ${colorScheme} ${width}`);
    }
  }
  await control.getByRole("button", { name: "Subir archivo" }).click();
  await expect(control.getByRole("status")).toHaveText("Archivo subido. La revisión se decide por separado.");
  await expect(control.getByRole("button", { name: "Subir archivo" })).toBeFocused();
  const item = control.locator(".evidence-list li").filter({ hasText: "Política de acceso" });
  await expect(item.getByText("politica-de-acceso.pdf")).toBeVisible();
  await expect(item.getByText("PDF · 338 kB")).toBeVisible();
  // evidence-malware-scanning spec: no download until GuardDuty's result says the file is clean.
  await expect(item.getByText("En análisis")).toBeVisible();
  await expect(item.getByRole("button", { name: /^Descargar/ })).toHaveCount(0);
  for (const width of [375, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await expectPolished(page, `uploaded file pending dark ${width}`);
  }
  status = "threats_found";
  await openEvidence();
  await expect(item.getByText("Bloqueado: posible malware")).toBeVisible();
  await expect(item.getByText(/Nadie puede descargarlo/)).toBeVisible();
  await expect(item.getByRole("button", { name: /^Descargar/ })).toHaveCount(0);
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    for (const width of [375, 1280]) {
      await page.setViewportSize({ width, height: 900 });
      await expectPolished(page, `blocked file ${colorScheme} ${width}`);
    }
  }
  status = "no_threats_found";
  await openEvidence();
  await expect(item.getByText("Sin amenazas detectadas")).toBeVisible();
  const download = page.waitForEvent("download");
  await item.getByRole("button", { name: "Descargar politica-de-acceso.pdf" }).click();
  expect((await download).suggestedFilename()).toBe("politica-de-acceso.pdf");
  tampered = true;
  await item.getByRole("button", { name: "Descargar politica-de-acceso.pdf" }).click();
  await expect(item.getByRole("alert")).toContainText("ya no coincide con el que se registró");
  await expectPolished(page, "integrity failure");
  expect(csp).toEqual([]);
});
