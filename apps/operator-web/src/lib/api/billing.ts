import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { unwrap } from "@atesta/ui/api-error";
import type { components } from "./schema";
import { api } from "./client";
import { organizationKey } from "./organizations";

export type PlanInfo = components["schemas"]["PlanInfo"];
export type SubscriptionIn = components["schemas"]["SubscriptionIn"];
export type BillingIn = components["schemas"]["BillingProfileIn"];
export const BILLING_FIELDS = ["legal_name", "tax_id", "address_line1", "address_line2", "postal_code", "city", "region", "country", "contact_email"] as const;
export type BillingField = (typeof BILLING_FIELDS)[number];

/** The plan editor's plans, limits, features and every add-on (`GET /plans`, admin and billing). */
export function usePlans() {
  return useQuery({ queryKey: ["plans"], staleTime: Infinity, queryFn: () => unwrap(api.GET("/api/v1/plans")) });
}

function useOrgWrite<T>(id: string, write: (body: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: write, onSuccess: () => client.invalidateQueries({ queryKey: organizationKey(id) }) });
}

export function useSetPlan(id: string) {
  return useOrgWrite(id, (body: SubscriptionIn) => unwrap(api.PUT("/api/v1/organizations/{org_id}/subscription", { params: { path: { org_id: id } }, body })));
}

export function useSetBilling(id: string) {
  return useOrgWrite(id, (body: BillingIn) => unwrap(api.PUT("/api/v1/organizations/{org_id}/billing-profile", { params: { path: { org_id: id } }, body })));
}
