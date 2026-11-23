import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { api } from "./client";
import { unwrap } from "./hooks";

export type AccessReviewSummary = components["schemas"]["AccessReviewSummary"];
export type AccessReview = components["schemas"]["AccessReviewOut"];
export type AccountInput = components["schemas"]["AccountIn"];
export type Policy = components["schemas"]["PolicyOut"];
export type DueItem = components["schemas"]["DueItem"];
export type TrainingCampaign = components["schemas"]["CampaignOut"];
export type Incident = components["schemas"]["IncidentOut"];
export type IncidentClock = components["schemas"]["ClockOut"];
export type IncidentCriterion = components["schemas"]["CriterionOut"];

const org = (orgId: string) => ({ params: { path: { org_id: orgId } } });

/**
 * Accounts from pasted lines or a CSV read in the browser (recorded-routines spec): one account
 * per line, an optional detail after the first comma or tab. A header row naming the columns is
 * skipped; blank lines and duplicates are dropped. Nothing is uploaded.
 */
export function parseAccounts(text: string): AccountInput[] {
  const seen = new Set<string>();
  const out: AccountInput[] = [];
  for (const [i, raw] of text.split(/\r?\n/).entries()) {
    const line = raw.trim();
    if (!line) continue;
    const cut = line.search(/[,;\t]/);
    const account = (cut === -1 ? line : line.slice(0, cut)).trim().replace(/^"|"$/g, "");
    const detail = (cut === -1 ? "" : line.slice(cut + 1)).trim().replace(/^"|"$/g, "");
    if (i === 0 && /^(account|cuenta|user|usuario|email|correo)$/i.test(account)) continue;
    const key = account.toLocaleLowerCase();
    if (!account || seen.has(key)) continue;
    seen.add(key);
    out.push({ account: account.slice(0, 320), detail: detail.slice(0, 200) });
  }
  return out;
}

export function useAccessReviews(orgId: string) {
  return useQuery({ queryKey: ["access-reviews", orgId], queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/access-reviews", org(orgId))) });
}

export function useAccessReview(orgId: string, reviewId: string) {
  return useQuery({
    queryKey: ["access-reviews", orgId, reviewId], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/access-reviews/{review_id}", { params: { path: { org_id: orgId, review_id: reviewId } } })),
  });
}

function useRoutineMutation<I, O>(orgId: string, fn: (input: I) => Promise<O>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => Promise.all([
      client.invalidateQueries({ queryKey: ["access-reviews", orgId] }),
      client.invalidateQueries({ queryKey: ["policies", orgId] }),
      client.invalidateQueries({ queryKey: ["routines-due", orgId] }),
      client.invalidateQueries({ queryKey: ["training", orgId] }),
      client.invalidateQueries({ queryKey: ["incidents", orgId] }),
    ]),
  });
}

export function useCreateAccessReview(orgId: string) {
  return useRoutineMutation(orgId, (body: components["schemas"]["AccessReviewIn"]) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/access-reviews", { ...org(orgId), body })));
}

export function useDecide(orgId: string, reviewId: string) {
  return useRoutineMutation(orgId, (body: components["schemas"]["DecisionIn"]) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/access-reviews/{review_id}/decisions", { params: { path: { org_id: orgId, review_id: reviewId } }, body })));
}

export function useCloseReview(orgId: string, reviewId: string) {
  return useRoutineMutation(orgId, () =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/access-reviews/{review_id}/close", { params: { path: { org_id: orgId, review_id: reviewId } } })));
}

export function usePolicies(orgId: string) {
  return useQuery({ queryKey: ["policies", orgId], queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/policies", org(orgId))) });
}

export function useCreatePolicy(orgId: string) {
  return useRoutineMutation(orgId, (body: components["schemas"]["PolicyIn"]) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/policies", { ...org(orgId), body })));
}

export function useApprovePolicy(orgId: string) {
  return useRoutineMutation(orgId, ({ policyId, body }: { policyId: string; body: components["schemas"]["ApprovalIn"] }) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/policies/{policy_id}/approvals", { params: { path: { org_id: orgId, policy_id: policyId } }, body })));
}

export function useRoutinesDue(orgId: string) {
  return useQuery({ queryKey: ["routines-due", orgId], retry: false, queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/routines/due", org(orgId))) });
}

export function useTrainingCampaigns(orgId: string) {
  return useQuery({ queryKey: ["training", orgId], queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/training-campaigns", org(orgId))) });
}

export function useTrainingCampaign(orgId: string, campaignId: string) {
  return useQuery({
    queryKey: ["training", orgId, campaignId], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/training-campaigns/{campaign_id}", { params: { path: { org_id: orgId, campaign_id: campaignId } } })),
  });
}

export function useCreateTraining(orgId: string) {
  return useRoutineMutation(orgId, (body: components["schemas"]["CampaignIn"]) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/training-campaigns", { ...org(orgId), body })));
}

export function useCloseTraining(orgId: string, campaignId: string) {
  return useRoutineMutation(orgId, () =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/training-campaigns/{campaign_id}/close", { params: { path: { org_id: orgId, campaign_id: campaignId } } })));
}

/** The public training link (no account): the token goes in the body, never in a URL. */
export function useTrainingLink(token: string | null) {
  return useQuery({
    queryKey: ["training-link", token], retry: false, enabled: token !== null,
    queryFn: () => unwrap(api.POST("/api/v1/training/link", { body: { token: token ?? "" } })),
  });
}

export function useAcknowledge() {
  return useMutation({
    mutationFn: (body: components["schemas"]["AcknowledgeIn"]) => unwrap(api.POST("/api/v1/training/acknowledge", { body })),
  });
}

export function useIncidents(orgId: string) {
  return useQuery({ queryKey: ["incidents", orgId], queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/incidents", org(orgId))) });
}

/** Official texts that explain the incident flags, from the active packs (recorded-routines spec). */
export function useIncidentCriteria(orgId: string) {
  return useQuery({ queryKey: ["incident-criteria", orgId], retry: false, queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/incidents/criteria", org(orgId))) });
}

export function useIncident(orgId: string, incidentId: string) {
  return useQuery({
    queryKey: ["incidents", orgId, incidentId], retry: false,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/incidents/{incident_id}", { params: { path: { org_id: orgId, incident_id: incidentId } } })),
  });
}

export function useCreateIncident(orgId: string) {
  return useRoutineMutation(orgId, (body: components["schemas"]["IncidentIn"]) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/incidents", { ...org(orgId), body })));
}

export function useIncidentUpdate(orgId: string, incidentId: string) {
  return useRoutineMutation(orgId, (body: components["schemas"]["UpdateIn"]) =>
    unwrap(api.POST("/api/v1/orgs/{org_id}/incidents/{incident_id}/updates", { params: { path: { org_id: orgId, incident_id: incidentId } }, body })));
}

/** SHA-256 of a file, computed in the browser; the file never leaves the device. */
export async function sha256Of(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
