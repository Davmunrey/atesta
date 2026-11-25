import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { unwrap } from "@atesta/ui/api-error";
import type { components } from "./schema";
import { api } from "./client";

export type OrganizationRow = components["schemas"]["OrganizationRow"];
export type OrganizationDetail = components["schemas"]["OrganizationDetail"];
export type OrgState = components["schemas"]["State"];
export type Health = components["schemas"]["Health"];
export const STATES: OrgState[] = ["active", "suspended", "closing"];
export const PLANS = ["starter", "pro", "business", "default"] as const;
export const SORTS = ["name", "created", "activity"] as const;

/** The list's search, filters, sort and page, kept in the page's address (operator-portal spec,
 *  screen 2). Unknown values fall back to none, so a pasted address never breaks the list. */
export type ListQuery = { q: string; state: OrgState | ""; plan: (typeof PLANS)[number] | ""; health: boolean; billing: boolean; sort: (typeof SORTS)[number]; page: number };

const pick = <T extends string>(values: readonly T[], value: string | null): T | "" => (values as readonly string[]).includes(value ?? "") ? value as T : "";

export function parseListQuery(params: URLSearchParams): ListQuery {
  const page = Number(params.get("page"));
  return {
    q: params.get("q")?.slice(0, 200) ?? "", state: pick(STATES, params.get("state")), plan: pick(PLANS, params.get("plan")),
    health: params.get("health") === "attention", billing: params.get("billing") === "missing",
    sort: pick(SORTS, params.get("sort")) || "name", page: Number.isInteger(page) && page > 1 ? page : 1,
  };
}

export function listAddress(query: ListQuery): string {
  const params = new URLSearchParams();
  if (query.q) params.set("q", query.q);
  if (query.state) params.set("state", query.state);
  if (query.plan) params.set("plan", query.plan);
  if (query.health) params.set("health", "attention");
  if (query.billing) params.set("billing", "missing");
  if (query.sort !== "name") params.set("sort", query.sort);
  if (query.page > 1) params.set("page", String(query.page));
  const text = params.toString();
  return text ? `/?${text}` : "/";
}

export function useOrganizations(query: ListQuery) {
  return useQuery({
    queryKey: ["organizations", query], placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET("/api/v1/organizations", { params: { query: {
      q: query.q || undefined, state: query.state || undefined, plan: query.plan || undefined,
      health: query.health ? "attention" : undefined, billing: query.billing ? "missing" : undefined, sort: query.sort, page: query.page,
    } } })),
  });
}

export const organizationKey = (id: string) => ["organization", id] as const;

export function useOrganization(id: string) {
  return useQuery({ queryKey: organizationKey(id), queryFn: () => unwrap(api.GET("/api/v1/organizations/{org_id}", { params: { path: { org_id: id } } })) });
}
