import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import type { Role } from "@/lib/permissions";
import { api } from "./client";
import { errorCode } from "./errors";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
  ) {
    super(code ?? `HTTP ${status}`);
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (data === undefined) throw new ApiError(response.status, errorCode(error));
  return data;
}

/** For 204 responses, which carry no body. */
export async function expectOk(call: Promise<{ error?: unknown; response: Response }>): Promise<void> {
  const { error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, errorCode(error));
}

export const ME = ["me"] as const;
const members = (orgId: string) => ["members", orgId] as const;
const invitations = (orgId: string) => ["invitations", orgId] as const;

export function useMeQuery() {
  return useQuery({ queryKey: ME, queryFn: () => unwrap(api.GET("/api/v1/me")), retry: false });
}

export function useCreateOrg() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unwrap(api.POST("/api/v1/orgs", { body: { name } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ME }),
  });
}

/** Auditors never see the people list (rbac spec), so their browser does not ask for it. */
export function useMembers(orgId: string, enabled = true) {
  const me = useQueryClient().getQueryData<components["schemas"]["MeOut"]>(ME);
  const auditor = me?.memberships.find((m) => m.organization_id === orgId)?.role === "auditor";
  return useQuery({
    queryKey: members(orgId), enabled: enabled && !auditor,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/members", { params: { path: { org_id: orgId } } })),
  });
}

export function useOverview(orgId: string) {
  return useQuery({
    queryKey: ["overview", orgId], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/overview", { params: { path: { org_id: orgId } } })),
  });
}

export function useFrameworkDetail(orgId: string, frameworkKey: string) {
  return useQuery({
    queryKey: ["framework", orgId, frameworkKey], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/frameworks/{framework_key}", { params: { path: { org_id: orgId, framework_key: frameworkKey } } })),
  });
}

type ReviewInput = { controlKey: string } & components["schemas"]["ReviewIn"];

/** A review changes the register now and the score once the rescore job runs. */
export function useRecordReview(orgId: string, frameworkKey: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ controlKey, ...body }: ReviewInput) =>
      unwrap(api.POST("/api/v1/orgs/{org_id}/controls/{control_key}/reviews", { params: { path: { org_id: orgId, control_key: controlKey } }, body })),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ["framework", orgId, frameworkKey] }),
        client.invalidateQueries({ queryKey: ["overview", orgId] }),
      ]),
  });
}

/** Role changes and removals can change the caller's own memberships, so /me refreshes too. */
function useMemberMutation<T>(orgId: string, mutationFn: (input: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: members(orgId) }),
        client.invalidateQueries({ queryKey: ME }),
      ]),
  });
}

export function useChangeRole(orgId: string) {
  return useMemberMutation(orgId, ({ userId, role, accessExpiresOn = null }: { userId: string; role: Role; accessExpiresOn?: string | null }) =>
    unwrap(
      api.PATCH("/api/v1/orgs/{org_id}/members/{user_id}", {
        params: { path: { org_id: orgId, user_id: userId } },
        body: { role, access_expires_on: accessExpiresOn },
      }),
    ),
  );
}

export function useRemoveMember(orgId: string) {
  return useMemberMutation(orgId, (userId: string) =>
    expectOk(
      api.DELETE("/api/v1/orgs/{org_id}/members/{user_id}", {
        params: { path: { org_id: orgId, user_id: userId } },
      }),
    ),
  );
}

export function useInvitations(orgId: string) {
  return useQuery({
    queryKey: invitations(orgId),
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/invitations", { params: { path: { org_id: orgId } } })),
  });
}

export function useCreateInvitation(orgId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; role: Role; access_expires_on?: string | null }) =>
      unwrap(api.POST("/api/v1/orgs/{org_id}/invitations", { params: { path: { org_id: orgId } }, body })),
    onSettled: () => client.invalidateQueries({ queryKey: invitations(orgId) }),
  });
}

export function useRevokeInvitation(orgId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) =>
      expectOk(
        api.DELETE("/api/v1/orgs/{org_id}/invitations/{invitation_id}", {
          params: { path: { org_id: orgId, invitation_id: invitationId } },
        }),
      ),
    onSettled: () => client.invalidateQueries({ queryKey: invitations(orgId) }),
  });
}

export function useAcceptInvitation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (token: string) => unwrap(api.POST("/api/v1/invitations/accept", { body: { token } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ME }),
  });
}

/** Organization activity from the audit log (insights spec); admins and owners only. */
export function useActivity(orgId: string, days: 30 | 90, enabled = true) {
  return useQuery({
    queryKey: ["activity", orgId, days], retry: false, enabled,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/activity", { params: { path: { org_id: orgId }, query: { days } } })),
  });
}

/** Closure (organization-closure spec): the erase date reaches every member through /me. */
export function useRequestClosure(orgId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (confirmName: string) =>
      unwrap(api.POST("/api/v1/orgs/{org_id}/closure", { params: { path: { org_id: orgId } }, body: { confirm_name: confirmName } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ME }),
  });
}

export function useCancelClosure(orgId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => expectOk(api.DELETE("/api/v1/orgs/{org_id}/closure", { params: { path: { org_id: orgId } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ME }),
  });
}
