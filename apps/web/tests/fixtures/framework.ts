import type { components } from "@/lib/api/schema";
import { overview } from "./overview";

/** Synthetic framework data, never a real normative pack. */
export const framework: components["schemas"]["FrameworkDetail"] = {
  key: "synthetic_alpha", name: "Synthetic Alpha", version: "2", status: "draft",
  source: "https://example.test/framework", catalog_version: "synthetic-2",
  catalog_matches_snapshot: false, snapshot: overview.frameworks[0]!.snapshot, development: true,
  requirements: [
    { code: "R1", title_es: "Protección de cuentas de prueba", title_en: "Test account protection",
      source: "https://example.test/requirement", applies_to: ["example"], in_current_catalog: true, status: "fail",
      controls: [{ key: "ctl.example", title_es: "Verificar acceso de prueba", title_en: "Verify test access",
        description_es: "Comprueba la configuración en el entorno de prueba y conserva el resultado.", description_en: "Check the setting in the test environment and retain the result.",
        manual: false, remediation_refs: ["https://example.test/guide", "javascript:alert(1)"],
        mapping_reviewed: false, mapping_source: "Synthetic mapping", observed_status: null,
        checks: [{ engine: "prowler", check_id: "synthetic_access_check", observed_status: null }] }] },
    { code: "R2", title_es: "Registro de revisión", title_en: "Review record", source: "synthetic", applies_to: [], in_current_catalog: true, status: "manual", controls: [] },
    { code: "R3", title_es: "Configuración pendiente de evaluar", title_en: "Setting awaiting evaluation", source: null, applies_to: [], in_current_catalog: true, status: "not_evaluated", controls: [] },
    { code: "R4", title_es: "Registro comprobado", title_en: "Checked record", source: null, applies_to: [], in_current_catalog: true, status: "pass", controls: [] },
    { code: "OLD", title_es: null, title_en: null, source: null, applies_to: [], in_current_catalog: false, status: "not_applicable", controls: [] },
  ],
};

export const preparationFramework: components["schemas"]["FrameworkDetail"] = {
  ...framework, snapshot: null, requirements: [],
  catalog_context: {
    content_state: "template", assessment_enabled: false,
    summary_es: "Plantilla sintética para preparar una revisión.", summary_en: "Synthetic preparation template.",
    scope_es: "Delimita los servicios de prueba.", scope_en: "Define test services.",
    applicability_es: "Justifica la selección con el revisor.", applicability_en: "Justify selection with the reviewer.",
    limitations_es: "Faltan requisitos y mapeos revisados.", limitations_en: "Reviewed requirements and mappings are missing.",
    preparation_controls: ["ctl.example"], source_refs: ["https://example.test/source"], verified_on: "2026-11-13",
  },
  preparation_controls: [{ key: "ctl.example", title_es: "Verificar acceso de prueba", title_en: "Verify test access",
    description_es: "1. Revisa el alcance.\n2. Conserva evidencia sintética.", description_en: "1. Review scope.\n2. Retain synthetic evidence.",
    manual: false, remediation_refs: ["https://example.test/guide"], checks: [{ engine: "prowler", check_id: "synthetic_access_check" }] }],
};

export const requirementGuidance: components["schemas"]["RequirementContext"] = {
  official_text_es: "Texto oficial sintético para probar presentación.", applicability_es: "Aplicación según dimensión.",
  selection_basis: "nivel · C I T A", selection_rules: [{ level: "BAJO", rule: "+ [R1 o R2]" }, { level: "ALTO", rule: "+ R3" }],
  section: "4.2.1", source_sha256: "a".repeat(64),
};

type Review = components["schemas"]["ReviewOut"];

/** A synthetic manual control, reviewed or not, on R2 (first in the register). */
export function withManualControl(review: Review | null): components["schemas"]["FrameworkDetail"] {
  const paper = {
    key: "ctl.paper", title_es: "Plan de respuesta sintético", title_en: "Synthetic response plan",
    description_es: "Aprueba y conserva el plan.", description_en: "Approve and keep the plan.", manual: true,
    remediation_refs: [], mapping_reviewed: true, mapping_source: "Synthetic mapping", observed_status: null,
    checks: [], review,
  };
  return { ...framework, requirements: [{ ...framework.requirements[1]!, controls: [paper] }, framework.requirements[0]!] };
}

export const passingReview: Review = {
  id: "22222222-2222-4222-8222-222222222222", control_key: "ctl.paper", status: "pass",
  rationale: "Acta del comité de 2026-10-01.\nPunto 3 aprobado.", valid_until: "2027-10-01",
  reviewed_by: "11111111-1111-4111-8111-111111111111", reviewed_at: "2026-10-02T09:30:00Z", expired: false,
};
