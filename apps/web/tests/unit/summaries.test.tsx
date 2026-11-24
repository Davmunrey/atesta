// @vitest-environment jsdom
import { cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { incidentSummary, policySummary, reviewSummary, tokenSummary, trainingSummary } from "@/lib/summaries";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const today = "2026-11-23";
const approval = (on: string) => ({ version: "1.0", approver_name: "Comité", approved_on: on, sha256: null, recorded_at: `${on}T00:00:00Z` });
const policy = (id: string, latest: string | null, next: string | null) => ({ id, title: id, location_url: "https://example.com/p", review_months: 12, created_at: "2026-01-01T00:00:00Z", latest: latest ? approval(latest) : null, next_review_on: next });

// Executive summary (#240): figures come from the list the page already loads.
it("counts policies approved and in date, overdue for review and never approved", () => {
  expect(policySummary([policy("a", "2026-01-10", "2027-01-10"), policy("b", "2025-01-10", "2026-01-10"), policy("c", null, null)], today))
    .toEqual({ total: 3, current: 1, overdue: 1, unapproved: 1 });
});

it("counts open and closed access reviews, accounts still to decide and reviews past their date", () => {
  const review = (id: string, pending: number, closed: boolean, due: string | null) => ({ id, title: id, system: "M365", due_on: due, created_at: "2026-11-01T00:00:00Z", closed_at: closed ? "2026-11-02T00:00:00Z" : null, total: 3, keep: 3 - pending, revoke: 0, pending });
  expect(reviewSummary([review("a", 2, false, "2026-11-01"), review("b", 1, false, null), review("c", 0, true, "2026-10-01")], today))
    .toEqual({ total: 3, open: 2, closed: 1, pending: 3, late: 1 });
});

it("counts open trainings and every confirmation", () => {
  const campaign = (id: string, acknowledged: number, closed: boolean) => ({ id, title: id, material_url: "https://example.com", closes_on: "2026-12-01", created_at: "2026-11-01T00:00:00Z", closed_at: closed ? "2026-11-02T00:00:00Z" : null, acknowledged });
  expect(trainingSummary([campaign("a", 3, true), campaign("b", 2, false)])).toEqual({ total: 2, open: 1, acknowledged: 5 });
});

it("counts open incidents and overdue notices of open incidents only", () => {
  const incident = (id: string, overdue: number, closed: boolean) => ({ id, title: id, aware_at: "2026-11-20T00:00:00Z", created_at: "2026-11-20T00:00:00Z", closed_at: closed ? "2026-11-21T00:00:00Z" : null, next_due_at: null, overdue, personal_data: false, significant: false });
  expect(incidentSummary([incident("a", 1, false), incident("b", 0, false), incident("c", 2, true)])).toEqual({ open: 2, closed: 1, overdue: 1, running: 0, nextDue: null });
  const running = (id: string, due: string) => ({ ...incident(id, 0, false), next_due_at: due });
  expect(incidentSummary([running("d", "2026-11-26T10:00:00Z"), running("e", "2026-11-25T10:00:00Z"), incident("f", 1, false)]))
    .toMatchObject({ open: 3, overdue: 1, running: 2, nextDue: "2026-11-25T10:00:00Z" });
});

it("counts active tokens, revoked or expired ones, and the latest use", () => {
  const token = (id: string, revoked: boolean, expires: string, used: string | null) => ({ id, name: id, prefix: "atesta_x", scopes: ["evidence:write"], rate_limit_per_minute: 60, read_only: false, created_at: "2026-11-01T00:00:00Z", created_by_email: "a@example.test", expires_at: expires, revoked_at: revoked ? "2026-11-10T00:00:00Z" : null, last_used_at: used });
  expect(tokenSummary([token("a", false, "2027-01-01T00:00:00Z", "2026-11-20T10:00:00Z"), token("b", true, "2027-01-01T00:00:00Z", "2026-11-22T10:00:00Z"), token("c", false, "2026-11-01T00:00:00Z", null)], new Date(`${today}T12:00:00Z`)))
    .toEqual({ active: 1, inactive: 2, lastUsed: "2026-11-22T10:00:00Z" });
});
