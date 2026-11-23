import { useQuery } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { api } from "./client";
import { unwrap } from "./hooks";

export type Report = components["schemas"]["Report"];

/** The monthly report for management (management-report spec). Opening it is an audit event. */
export function useReport(orgId: string, month: string) {
  return useQuery({
    queryKey: ["report", orgId, month], retry: false, staleTime: Infinity,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/report", { params: { path: { org_id: orgId }, query: { month } } })),
  });
}
