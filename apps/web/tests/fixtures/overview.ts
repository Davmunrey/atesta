import type { components } from "@/lib/api/schema";

const snapshot = {
  id: "11111111-1111-4111-8111-111111111111", scan_id: "22222222-2222-4222-8222-222222222222",
  framework_version: "1", catalog_version: "synthetic-1", score: 66.7, passed: 2, failed: 1,
  manual: 1, not_applicable: 0, computed_at: "2026-11-13T10:00:00Z",
};

/** Synthetic UI fixtures only. Never imported by application code or presented as a real pack. */
export const overview: components["schemas"]["OverviewOut"] = {
  development: true, evidence_count: 4,
  frameworks: [
    { key: "synthetic_alpha", name: "Synthetic Alpha", version: "2", status: "released", requirements: 5, snapshot },
    { key: "synthetic_beta", name: "Synthetic Beta", version: "1", status: "draft", requirements: 3, snapshot: { ...snapshot, id: "other", score: 0, passed: 0, failed: 3 } },
    { key: "synthetic_gamma", name: "Synthetic Gamma", version: "1", status: "released", requirements: 2, snapshot: { ...snapshot, id: "manual", score: null, passed: 0, failed: 0, manual: 4 } },
    { key: "synthetic_delta", name: "Synthetic Delta", version: "1", status: "released", requirements: 0, snapshot: null },
  ],
  scans: [
    { id: snapshot.scan_id, provider: "m365", status: "partial", evaluated_checks: 7, expected_checks: 10, queued_at: "2026-11-13T09:45:00Z", finished_at: "2026-11-13T10:00:00Z" },
    { id: "33333333-3333-4333-8333-333333333333", provider: "google_workspace", status: "blocked", evaluated_checks: 0, expected_checks: 0, queued_at: "2026-11-12T09:45:00Z", finished_at: null },
  ],
};

export const emptyOverview: components["schemas"]["OverviewOut"] = {
  development: false, evidence_count: 0, frameworks: [], scans: [],
};
