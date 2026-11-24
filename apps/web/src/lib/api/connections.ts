import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { api } from "./client";
import { ApiError, unwrap } from "./hooks";

/** Connections (scanner-connectors and web-connections specs). The API decides every action. */
export type Connection = components["schemas"]["ConnectionOut"];
export type ConnectionDetail = components["schemas"]["ConnectionDetail"];

/** Statuses that still admit sign-in and consent (connections service, ONBOARDING). */
export const ONBOARDING: ReadonlySet<string> = new Set(["pending_setup", "incomplete", "over_privileged", "revoked"]);
const POLL_MS = 5000;
const MICROSOFT_LOGIN = "https://login.microsoftonline.com";

const key = (orgId: string) => ["connections", orgId] as const;
const org = (orgId: string) => ({ params: { path: { org_id: orgId } } });
const one = (orgId: string, id: string) => ({ params: { path: { org_id: orgId, connection_id: id } } });

/** True only for Microsoft's sign-in origin over https: the one place Connect may navigate to. */
export function isMicrosoftLogin(url: string): boolean {
  try {
    return new URL(url).origin === MICROSOFT_LOGIN;
  } catch {
    return false;
  }
}

/** The org's connections; refreshed every 5 seconds while one is being verified. */
export function useConnections(orgId: string) {
  return useQuery({
    queryKey: key(orgId),
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/connections", org(orgId))),
    refetchInterval: (query) => (query.state.data?.some((c) => c.status === "verifying") ? POLL_MS : false),
  });
}

/** One connection's detail, fetched when its permissions are opened. */
export function useConnection(orgId: string, id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...key(orgId), id], enabled,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/connections/{connection_id}", one(orgId, id))),
  });
}

function useAction<T, V>(orgId: string, run: (v: V) => Promise<T>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: run, onSettled: () => client.invalidateQueries({ queryKey: key(orgId) }) });
}

export function useCreateConnection(orgId: string) {
  return useAction(orgId, (body: components["schemas"]["ConnectionIn"]) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/connections", { ...org(orgId), body })));
}

/** Starts the Microsoft sign-in; resolves to the URL only when it is Microsoft's. */
export function useStartSignIn(orgId: string) {
  return useMutation({
    mutationFn: async (id: string) => {
      const { authorize_url: url } = await unwrap(api.POST("/api/v1/orgs/{org_id}/connections/{connection_id}/m365/signin", one(orgId, id)));
      if (!isMicrosoftLogin(url)) throw new ApiError(502, null); // shown as the generic message
      return url;
    },
  });
}

export function useVerify(orgId: string) {
  return useAction(orgId, (id: string) => unwrap(api.POST("/api/v1/orgs/{org_id}/connections/{connection_id}/verify", one(orgId, id))));
}

/** Google onboarding step 3: the super admin Atesta reads as (web-connections spec, issue 425). */
export function useSetGoogleSubject(orgId: string) {
  return useAction(orgId, ({ id, ...body }: { id: string } & components["schemas"]["GoogleSubjectIn"]) =>
    unwrap(api.PUT("/api/v1/orgs/{org_id}/connections/{connection_id}/google", { ...one(orgId, id), body })));
}

export function useScanNow(orgId: string) {
  return useAction(orgId, (id: string) => unwrap(api.POST("/api/v1/orgs/{org_id}/connections/{connection_id}/scans", one(orgId, id))));
}

export function useDisconnect(orgId: string) {
  return useAction(orgId, (id: string) => unwrap(api.DELETE("/api/v1/orgs/{org_id}/connections/{connection_id}", one(orgId, id))));
}
