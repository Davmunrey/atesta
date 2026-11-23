// @vitest-environment jsdom
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DossierView } from "@/components/dossier-view";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const auditor = { organization_id: "primary", organization_name: "Synthetic Team", role: "auditor" as const, access_expires_on: "2027-01-01", closure_erase_after: null };
const url = "/api/v1/orgs/primary/frameworks/ens/dossier";
const dossier = {
  framework_key: "ens", framework_name: "ENS · RD 311/2022", framework_version: "draft6", catalog_version: "abc123", generated_at: "2026-11-23T12:00:00Z",
  statement: "Not a certification", signer: { name: null, role: null, date: null, signature: null },
  summary: {
    counts: { key: "ens", name: "ENS", total: 73, assessed: 10, implemented: 6, partial: 2, not_implemented: 1, not_applicable: 1, has_axes: true, scope_defined: true,
      review_on: null, overdue: 2, unowned_open: 0, open_by_owner: {}, last_assessed_at: null },
    review: { reviewer_name: "Ana Pérez", reviewer_role: "Responsable de seguridad", reviewed_on: "2026-11-20", conclusions: "Avance correcto.", corrective_actions: "", recorded_by: "u1", recorded_at: "2026-11-20T10:00:00Z" },
    routines: { policies_due: 1, policies_unapproved: 0, access_reviews_overdue: 0, trainings_unclosed: 0, incident_clocks_overdue: 0 },
  },
  applicability: [{ code: "op.acc.6", title_es: "Mecanismo de autenticación", decision: "applies", decided_by_person: true, rule: null, level: null, justification: "Usuarios internos.", implementation: "implemented" }],
  requirements: [{ code: "op.acc.6", title_es: "Mecanismo de autenticación", title_en: null, source: "https://example.test", decision: "applies", implementation: "implemented", justification: "",
    controls: [{ key: "ctl.admin_mfa", title_es: "MFA de administradores", title_en: "Administrator MFA", manual: false, observed_status: "pass", review: null,
      evidence: [{ title: "Prueba de restauración", statement: "Restauración correcta.", reference_url: "https://ci.example.test/run/1", collected_at: "2026-11-22T08:00:00Z", source_type: "api" }] }] }],
  routines: { policies: [], access_reviews: [], trainings: [], incidents: [] },
};

it("gathers the management summary, applicability and evidence by requirement", async () => {
  stubApi({ [`GET ${url}`]: [200, dossier] });
  renderWithProviders(<DossierView org={auditor} frameworkKey="ens" />);
  const summary = await screen.findByRole("region", { name: "Resumen para dirección" });
  expect(within(summary).getByText("73")).toBeTruthy();
  expect(within(summary).getByText(/Ana Pérez \(Responsable de seguridad\), 20 de noviembre de 2026/)).toBeTruthy();
  expect(within(summary).getByText("1 política por revisar")).toBeTruthy();
  const evidence = screen.getByRole("region", { name: "Evidencias por requisito" });
  expect(within(evidence).getByText(/Comprobación superada/)).toBeTruthy();
  expect(within(evidence).getByText(/Enviada por una herramienta/)).toBeTruthy();
  expect(screen.getByText(/No es una certificación/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Imprimir o guardar en PDF" })).toBeTruthy();
});

it("reads in English, keeping official Spanish titles marked", async () => {
  stubApi({ [`GET ${url}`]: [200, dossier] });
  renderWithProviders(<DossierView org={auditor} frameworkKey="ens" />, "en");
  expect(await screen.findByRole("region", { name: "Management summary" })).toBeTruthy();
  const title = screen.getByRole("region", { name: "Evidence by requirement" }).querySelector("h3 [lang='es']");
  expect(title?.textContent).toBe("Mecanismo de autenticación");
  expect(screen.getByText("Administrator MFA")).toBeTruthy();
});

it("shows the expected evidence of a requirement that has no controls yet, opened only while printing", async () => {
  const withEvidence = { ...dossier, requirements: [...dossier.requirements, { code: "org.1", title_es: "Política de seguridad", title_en: null, source: null, decision: "undecided", implementation: null, justification: "", controls: [],
    expected_evidence: { reviewed_by: null, items: [{ es: "Política aprobada por la dirección.", en: "Policy approved by management.", ref: { guide: "CCN-STIC 808", edition: "2026-04", section: "6.2.1 (org.1)", page: 18 } }] } }] };
  stubApi({ [`GET ${url}`]: [200, withEvidence] });
  renderWithProviders(<DossierView org={auditor} frameworkKey="ens" />);
  const evidence = await screen.findByRole("region", { name: "Evidencias por requisito" });
  const disclosure = within(evidence).getByText("Política aprobada por la dirección.").closest("details")!;
  expect(disclosure.hasAttribute("open")).toBe(false);
  window.dispatchEvent(new Event("beforeprint"));
  expect(disclosure.hasAttribute("open")).toBe(true);
  window.dispatchEvent(new Event("afterprint"));
  expect(disclosure.hasAttribute("open")).toBe(false);
  expect(within(disclosure).getByText("Referencia: CCN-STIC 808 (abril de 2026), apartado 6.2.1 (org.1), pág. 18")).toBeTruthy();
});

it("names the evidence each manual review cites, and says when a review cites none (issue 321)", async () => {
  const review = { id: "r1", control_key: "ctl.paper", status: "pass" as const, rationale: "Acta.", valid_until: "2027-10-01", reviewed_by: "u1",
    reviewed_at: "2026-10-02T09:30:00Z", expired: false, evidence: [{ id: "e1", title: "Acta del comité", kind: "attestation", collected_at: "2026-10-01T10:00:00Z" }] };
  const paper = { key: "ctl.paper", title_es: "Política", title_en: "Policy", manual: true, observed_status: "manual", review, evidence: [] };
  const old = { ...paper, key: "ctl.old", title_es: "Antigua", review: { ...review, evidence: [] } };
  const withReviews = { ...dossier, requirements: [{ ...dossier.requirements[0]!, controls: [paper, old] }] };
  stubApi({ [`GET ${url}`]: [200, withReviews] });
  renderWithProviders(<DossierView org={auditor} frameworkKey="ens" />);
  const evidence = await screen.findByRole("region", { name: "Evidencias por requisito" });
  expect(within(evidence).getByText("Cita una evidencia: Acta del comité.")).toBeTruthy();
  expect(within(evidence).getByText("La revisión no cita evidencias.")).toBeTruthy();
});
