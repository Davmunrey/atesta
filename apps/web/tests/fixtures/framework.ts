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
