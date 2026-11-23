import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { api } from "./client";
import { expectOk, unwrap } from "./hooks";

export type ApiToken = components["schemas"]["TokenOut"];

const org = (orgId: string) => ({ params: { path: { org_id: orgId } } });

/** API tokens (evidence-ingestion-api spec); admins only. */
export function useApiTokens(orgId: string, enabled = true) {
  return useQuery({ queryKey: ["api-tokens", orgId], enabled, queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/api-tokens", org(orgId))) });
}

export function useCreateApiToken(orgId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["TokenIn"]) => unwrap(api.POST("/api/v1/orgs/{org_id}/api-tokens", { ...org(orgId), body })),
    onSettled: () => client.invalidateQueries({ queryKey: ["api-tokens", orgId] }),
  });
}

export function useRevokeApiToken(orgId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (tokenId: string) =>
      expectOk(api.DELETE("/api/v1/orgs/{org_id}/api-tokens/{token_id}", { params: { path: { org_id: orgId, token_id: tokenId } } })),
    onSettled: () => client.invalidateQueries({ queryKey: ["api-tokens", orgId] }),
  });
}

/** A ready-to-run example for the token just created; the control key is a real common control. */
export function curlExample(origin: string, token: string): string {
  return [
    `curl -X POST ${origin}/api/v1/ingest/evidence \\`,
    `  -H "Authorization: Bearer ${token}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"control": "ctl.continuity_restore", "title": "Prueba de restauración", "statement": "La restauración nocturna terminó sin errores.", "source": "github-actions", "external_id": "run-1"}'`,
  ].join("\n");
}
