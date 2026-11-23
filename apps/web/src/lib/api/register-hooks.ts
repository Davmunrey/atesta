import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { api } from "./client";
import { unwrap } from "./hooks";

export type Register = components["schemas"]["Register"];
export type RegisterItem = components["schemas"]["RegisterItem"];
export type AssessmentInput = components["schemas"]["AssessmentIn"];
export type AssessmentReviewInput = components["schemas"]["AssessmentReviewIn"];
export type AxisValues = components["schemas"]["ScopeIn"]["axis_values"];

const key = (orgId: string, frameworkKey: string) => ["register", orgId, frameworkKey] as const;
const path = (orgId: string, frameworkKey: string) => ({ path: { org_id: orgId, framework_key: frameworkKey } });

/** The organization's own register (requirement-register spec). A 404 means the framework has none. */
export function useRegister(orgId: string, frameworkKey: string) {
  return useQuery({
    queryKey: key(orgId, frameworkKey), retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/frameworks/{framework_key}/register", { params: path(orgId, frameworkKey) })),
  });
}

function useRegisterMutation<T>(orgId: string, frameworkKey: string, mutationFn: (input: T) => Promise<unknown>) {
  const client = useQueryClient();
  // Invalidating the register prefix also refreshes its history.
  return useMutation({ mutationFn, onSuccess: () => client.invalidateQueries({ queryKey: key(orgId, frameworkKey) }) });
}

export function useRecordScope(orgId: string, frameworkKey: string) {
  return useRegisterMutation(orgId, frameworkKey, (axis_values: AxisValues) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/frameworks/{framework_key}/scope", { params: path(orgId, frameworkKey), body: { axis_values } })));
}

export function useRecordAssessment(orgId: string, frameworkKey: string) {
  return useRegisterMutation(orgId, frameworkKey, ({ code, body }: { code: string; body: AssessmentInput }) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/frameworks/{framework_key}/register/{requirement_code}", {
      params: { path: { org_id: orgId, framework_key: frameworkKey, requirement_code: code } }, body,
    })));
}

export function useRecordAssessmentReview(orgId: string, frameworkKey: string) {
  return useRegisterMutation(orgId, frameworkKey, (body: AssessmentReviewInput) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/frameworks/{framework_key}/assessment-reviews", { params: path(orgId, frameworkKey), body })));
}

/** Same-origin download links; the session cookie authenticates them. */
/** The CSV is written in the interface language (i18n-complete spec); JSON stays neutral. */
export function applicabilityUrl(orgId: string, frameworkKey: string, format: "csv" | "json", locale = "es"): string {
  const base = `/api/v1/orgs/${encodeURIComponent(orgId)}/frameworks/${encodeURIComponent(frameworkKey)}/applicability`;
  return format === "csv" ? `${base}.csv?lang=${encodeURIComponent(locale)}` : base;
}

export type Progress = { total: number; applies: number; notApplicable: number; assessed: number; implemented: number; partial: number };

/** Counts from the organization's recorded assessments; a proposal never counts as a decision. */
export function registerProgress(items: RegisterItem[]): Progress {
  const assessed = items.filter((i) => i.assessment);
  const applying = assessed.filter((i) => i.assessment!.applicability === "applies");
  return {
    total: items.length,
    assessed: assessed.length,
    applies: applying.length,
    notApplicable: assessed.length - applying.length,
    implemented: applying.filter((i) => i.assessment!.implementation === "implemented").length,
    partial: applying.filter((i) => i.assessment!.implementation === "partially_implemented").length,
  };
}

/** Requirements grouped by their code prefix (the code without its last segment), in code order. */
export function groupByPrefix<T extends { code: string }>(items: T[]): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const prefix = item.code.includes(".") ? item.code.slice(0, item.code.lastIndexOf(".")) : item.code;
    groups.set(prefix, [...(groups.get(prefix) ?? []), item]);
  }
  return [...groups.entries()];
}

export type HistoryPoint = components["schemas"]["HistoryPoint"];
export type AssignmentInput = components["schemas"]["AssignmentIn"];

export function useRegisterHistory(orgId: string, frameworkKey: string) {
  return useQuery({
    queryKey: [...key(orgId, frameworkKey), "history"], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/frameworks/{framework_key}/register/history", { params: path(orgId, frameworkKey) })),
  });
}

export function useScoreTrend(orgId: string, frameworkKey: string) {
  return useQuery({
    queryKey: ["trend", orgId, frameworkKey], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/frameworks/{framework_key}/trend", { params: path(orgId, frameworkKey) })),
  });
}

export function useRecordAssignment(orgId: string, frameworkKey: string) {
  return useRegisterMutation(orgId, frameworkKey, ({ code, body }: { code: string; body: AssignmentInput }) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/frameworks/{framework_key}/register/{requirement_code}/assignment", {
      params: { path: { org_id: orgId, framework_key: frameworkKey, requirement_code: code } }, body,
    })));
}

/** Not implemented and past its due date: the one state an owner must act on now. */
export function isOverdue(item: RegisterItem, today: string): boolean {
  const due = item.assignment?.due_on;
  const done = item.assessment?.applicability === "not_applicable" || item.assessment?.implementation === "implemented";
  return Boolean(due && due < today && !done);
}

/** Open measures (applicable and not yet implemented) per owner id; null collects the unowned. */
export function workload(items: RegisterItem[]): Map<string | null, number> {
  const counts = new Map<string | null, number>();
  for (const item of items) {
    const done = item.assessment?.applicability === "not_applicable" || item.assessment?.implementation === "implemented";
    if (done) continue;
    const owner = item.assignment?.owner_user_id ?? null;
    counts.set(owner, (counts.get(owner) ?? 0) + 1);
  }
  return counts;
}

export type MyWorkItem = components["schemas"]["MyWorkItem"];

/** Mi trabajo: the measures assigned to the signed-in person, across frameworks (rbac spec). */
export function useMyWork(orgId: string) {
  return useQuery({
    queryKey: ["my-work", orgId], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/my-work", { params: { path: { org_id: orgId } } })),
  });
}

/** A Mi trabajo row is overdue on the same rule as the register: past due and still open. */
export function isMyWorkOverdue(item: MyWorkItem, today: string): boolean {
  const done = item.applicability === "not_applicable" || item.implementation === "implemented";
  return Boolean(item.due_on && item.due_on < today && !done);
}

export type Readiness = components["schemas"]["FrameworkReadiness"];

/** Self-assessment counts per framework for the dashboard cockpit (readiness-cockpit spec). */
export function useReadiness(orgId: string) {
  return useQuery({
    queryKey: ["readiness", orgId], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/readiness", { params: { path: { org_id: orgId } } })),
  });
}

/** Global search over the catalog's requirements (console-shell spec); 2 characters or more. */
export function useSearch(orgId: string, q: string) {
  return useQuery({
    queryKey: ["search", orgId, q], retry: false, enabled: q.length >= 2, staleTime: 60_000,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/search", { params: { path: { org_id: orgId }, query: { q } } })),
  });
}
