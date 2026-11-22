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
export function applicabilityUrl(orgId: string, frameworkKey: string, format: "csv" | "json"): string {
  const base = `/api/v1/orgs/${encodeURIComponent(orgId)}/frameworks/${encodeURIComponent(frameworkKey)}/applicability`;
  return format === "csv" ? `${base}.csv` : base;
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
