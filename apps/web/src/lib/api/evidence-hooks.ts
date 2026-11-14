import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "./schema";
import { api } from "./client";
import { unwrap } from "./hooks";

export const EVIDENCE_PAGE_SIZE = 20;
const path = "/api/v1/orgs/{org_id}/controls/{control_key}/evidence";

export function useControlEvidence(orgId: string, controlKey: string, offset: number, enabled = true) {
  return useQuery({
    queryKey: ["evidence", orgId, controlKey, offset], retry: false, enabled,
    queryFn: () => unwrap(api.GET(path, { params: {
      path: { org_id: orgId, control_key: controlKey }, query: { offset, limit: EVIDENCE_PAGE_SIZE },
    } })),
  });
}

export function useRecordEvidence(orgId: string, controlKey: string) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: (body: components["schemas"]["StatementIn"]) => unwrap(api.POST(path, {
      params: { path: { org_id: orgId, control_key: controlKey } }, body,
    })),
    onSuccess: () => Promise.all([
      client.invalidateQueries({ queryKey: ["evidence", orgId, controlKey] }),
      client.invalidateQueries({ queryKey: ["overview", orgId] }),
    ]),
  });
}
