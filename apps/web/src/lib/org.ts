import type { components } from "@/lib/api/schema";

export type Membership = components["schemas"]["MembershipOut"];

/** The membership named in the URL; null when absent or not one of the user's orgs. */
export function selectOrg(memberships: Membership[], requested: string | null): Membership | null {
  return memberships.find((m) => m.organization_id === requested) ?? null;
}

export const orgHome = (orgId: string): string => `/app/org?org=${encodeURIComponent(orgId)}`;

export const orgDossier = (orgId: string, key: string): string =>
  `/app/dossier?org=${encodeURIComponent(orgId)}&framework=${encodeURIComponent(key)}`;

export const orgFrameworks = (orgId: string): string => `/app/frameworks?org=${encodeURIComponent(orgId)}`;

export const orgFramework = (orgId: string, key: string): string =>
  `/app/framework?org=${encodeURIComponent(orgId)}&framework=${encodeURIComponent(key)}`;

export const orgMembers = (orgId: string): string => `/app/members?org=${encodeURIComponent(orgId)}`;

export const orgInvitations = (orgId: string): string =>
  `/app/invitations?org=${encodeURIComponent(orgId)}`;

export const orgSettings = (orgId: string): string => `/app/settings?org=${encodeURIComponent(orgId)}`;

export const orgAccessReviews = (orgId: string): string => `/app/access-reviews?org=${encodeURIComponent(orgId)}`;

export const orgAccessReview = (orgId: string, id: string): string =>
  `/app/access-review?org=${encodeURIComponent(orgId)}&id=${encodeURIComponent(id)}`;

export const orgPolicies = (orgId: string): string => `/app/policies?org=${encodeURIComponent(orgId)}`;
export const orgTraining = (orgId: string): string => `/app/training-campaigns?org=${encodeURIComponent(orgId)}`;
export const orgTrainingCampaign = (orgId: string, id: string): string =>
  `/app/training-campaign?org=${encodeURIComponent(orgId)}&id=${encodeURIComponent(id)}`;
export const orgIncidents = (orgId: string): string => `/app/incidents?org=${encodeURIComponent(orgId)}`;
export const orgIncident = (orgId: string, id: string): string =>
  `/app/incident?org=${encodeURIComponent(orgId)}&id=${encodeURIComponent(id)}`;

export const orgIntegrations = (orgId: string): string => `/app/integrations?org=${encodeURIComponent(orgId)}`;

export const orgReport = (orgId: string): string => `/app/report?org=${encodeURIComponent(orgId)}`;

export const orgMyWork = (orgId: string): string => `/app/my-work?org=${encodeURIComponent(orgId)}`;

export const orgActivity = (orgId: string): string => `/app/activity?org=${encodeURIComponent(orgId)}`;
