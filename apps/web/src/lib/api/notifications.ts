import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { api } from "./client";
import { unwrap } from "./hooks";

/** Email notification preferences and one-click unsubscribe (notifications spec, PR 1). */
export type Preference = components["schemas"]["PreferenceOut"];
export type Kind = Preference["kind"];

const key = (orgId: string) => ["notification-preferences", orgId] as const;
const org = (orgId: string) => ({ params: { path: { org_id: orgId } } });

export function usePreferences(orgId: string) {
  return useQuery({ queryKey: key(orgId), queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/notifications/preferences", org(orgId))) });
}

export function useChangePreference(orgId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["PreferenceIn"]) =>
      unwrap(api.PUT("/api/v1/orgs/{org_id}/notifications/preferences", { ...org(orgId), body })),
    onSuccess: (saved) => client.setQueryData(key(orgId), saved),
    onSettled: () => client.invalidateQueries({ queryKey: key(orgId) }),
  });
}

/** The token goes in the query string the API expects; the page itself never logs it. */
export function useUnsubscribe() {
  return useMutation({
    mutationFn: (token: string) => unwrap(api.POST("/api/v1/unsubscribe", { params: { query: { token } } })),
  });
}
