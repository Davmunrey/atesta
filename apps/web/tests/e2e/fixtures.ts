/** A synthetic dossier for e2e routes that need one without a recorded catalog. */
export const dossier = {
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
