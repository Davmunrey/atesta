import { useQuery } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { api } from "./client";
import { unwrap } from "@atesta/ui/api-error";

export type Dossier = components["schemas"]["Dossier"];

/** The auditor dossier of one framework (auditor-dossier spec). Opening it is an audit event. */
export function useDossier(orgId: string, frameworkKey: string) {
  return useQuery({
    queryKey: ["dossier", orgId, frameworkKey], retry: false, staleTime: Infinity,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/frameworks/{framework_key}/dossier", { params: { path: { org_id: orgId, framework_key: frameworkKey } } })),
  });
}
