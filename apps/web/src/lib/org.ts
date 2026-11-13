import type { components } from "@/lib/api/schema";

export type Membership = components["schemas"]["MembershipOut"];

/** The membership named in the URL; null when absent or not one of the user's orgs. */
export function selectOrg(memberships: Membership[], requested: string | null): Membership | null {
  return memberships.find((m) => m.organization_id === requested) ?? null;
}

export const orgHome = (orgId: string): string => `/app/org?org=${encodeURIComponent(orgId)}`;

export const orgMembers = (orgId: string): string => `/app/members?org=${encodeURIComponent(orgId)}`;

export const orgInvitations = (orgId: string): string =>
  `/app/invitations?org=${encodeURIComponent(orgId)}`;
