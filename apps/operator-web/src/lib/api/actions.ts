import { useMutation, useQueryClient } from "@tanstack/react-query";
import { expectOk, unwrap } from "@atesta/ui/api-error";
import type { components } from "./schema";
import { api } from "./client";
import { organizationKey } from "./organizations";

export type ReasonCode = components["schemas"]["ReasonCode"];
export const REASON_CODES: ReasonCode[] = ["non_payment", "contract_ended", "customer_request", "security_review", "other"];
type Confirmed = { confirm_name: string; reason: string };

function useWrite<T>(id: string, call: (body: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: call, onSuccess: () => client.invalidateQueries({ queryKey: organizationKey(id) }) });
}

/** The admin's actions on an organization (operator-portal spec, screens 6 to 8); each refreshes
 *  the detail, whose state the next form depends on. */
export function useActions(id: string) {
  const path = { params: { path: { org_id: id } } };
  return {
    suspend: useWrite(id, (body: Confirmed & { reason_code: ReasonCode }) => unwrap(api.POST("/api/v1/organizations/{org_id}/suspension", { ...path, body }))),
    reactivate: useWrite(id, (reason: string) => expectOk(api.DELETE("/api/v1/organizations/{org_id}/suspension", { ...path, body: { reason } }))),
    askExport: useWrite(id, (reason: string) => expectOk(api.POST("/api/v1/organizations/{org_id}/export-request", { ...path, body: { reason } }))),
    startClosure: useWrite(id, (body: Confirmed) => unwrap(api.POST("/api/v1/organizations/{org_id}/closure", { ...path, body }))),
    cancelClosure: useWrite(id, (reason: string) => expectOk(api.DELETE("/api/v1/organizations/{org_id}/closure", { ...path, body: { reason } }))),
    requestErasure: useWrite(id, (body: Confirmed) => unwrap(api.POST("/api/v1/organizations/{org_id}/erasure-requests", { ...path, body }))),
    approveErasure: useWrite(id, ({ erasure, ...body }: Confirmed & { erasure: string }) =>
      unwrap(api.POST("/api/v1/erasure-requests/{erasure_id}/approval", { params: { path: { erasure_id: erasure } }, body }))),
    cancelErasure: useWrite(id, ({ erasure, reason }: { erasure: string; reason: string }) =>
      expectOk(api.DELETE("/api/v1/erasure-requests/{erasure_id}", { params: { path: { erasure_id: erasure } }, body: { reason } }))),
  };
}
