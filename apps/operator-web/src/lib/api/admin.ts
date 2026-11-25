import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { unwrap } from "@atesta/ui/api-error";
import type { components } from "./schema";
import { api } from "./client";

export type StaffMember = components["schemas"]["StaffOut"];
export type EventFilters = { org_id: string; staff_id: string; action: string; page: number };
/** Every action the operator trail records (operator-portal spec, "Audit events"). */
export const ACTIONS = ["organizations.searched", "organization.viewed", "billing_profile.viewed", "operator.plan_changed",
  "operator.billing_profile_updated", "operator.suspended", "operator.reactivated", "operator.export_requested", "operator.closure_started",
  "operator.closure_cancelled", "operator.erasure_requested", "operator.erasure_approved", "operator.erasure_cancelled",
  "staff.role_changed", "staff.disabled", "staff.enabled", "erasure.executed"] as const;

const STAFF = ["staff"] as const;

/** Screen 10 (admin): every staff member, enabled or not. */
export function useStaffList() {
  return useQuery({ queryKey: STAFF, queryFn: () => unwrap(api.GET("/api/v1/staff")) });
}

export function useChangeStaff() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; reason: string; role?: StaffMember["role"]; disabled?: boolean }) =>
      unwrap(api.PATCH("/api/v1/staff/{staff_id}", { params: { path: { staff_id: id } }, body })),
    onSuccess: () => client.invalidateQueries({ queryKey: STAFF }),
  });
}

/** Screen 11 (admin): the operator trail, filtered and paged. */
export function useEvents(filters: EventFilters) {
  return useQuery({
    queryKey: ["operator-events", filters], placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET("/api/v1/operator-events", { params: { query: {
      org_id: filters.org_id || undefined, staff_id: filters.staff_id || undefined, action: filters.action || undefined, page: filters.page,
    } } })),
  });
}

/** Screen 9 (admin): erasure receipts, 50 per page. */
export function useReceipts(page: number) {
  return useQuery({ queryKey: ["erasure-receipts", page], placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET("/api/v1/erasure-receipts", { params: { query: { page } } })) });
}
