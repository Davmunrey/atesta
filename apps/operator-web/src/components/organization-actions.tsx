"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { Badge } from "@atesta/ui/badge";
import { Panel } from "@atesta/ui/page-frame";
import { useActions } from "@/lib/api/actions";
import type { OrganizationDetail } from "@/lib/api/organizations";
import { ActionForm } from "./action-form";

const ERASURE = { pending: "erasurePending", approved: "erasureApproved", cancelled: "erasureCancelled", executed: "erasureExecuted" } as const;

/** Screens 6 to 8 of the operator-portal spec, for admins: suspension, export and closure, erasure. */
export function OrganizationActions({ org }: { org: OrganizationDetail }) {
  const t = useTranslations("actions");
  const format = useFormatter();
  const a = useActions(org.id);
  const [asked, setAsked] = useState(false);
  const day = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "long" });
  const erasure = org.erasure && org.erasure.state !== "cancelled" ? org.erasure : null;
  return <div className="panel-grid panel-grid-halves">
    <Panel title={t("suspension")} description={t(org.suspended_at ? "suspendedHelp" : "suspendHelp")} className="danger-zone panel-flow">
      {org.suspended_at
        ? <ActionForm label={t("reactivate")} submit={t("reactivate")} mutation={a.reactivate} onSubmit={(v, done) => a.reactivate.mutate(v.reason, { onSuccess: done })} />
        : <ActionForm label={t("suspend")} submit={t("suspend")} danger codes confirmName={org.name} mutation={a.suspend}
          onSubmit={(v, done) => a.suspend.mutate(v, { onSuccess: done })} />}
    </Panel>
    <Panel title={t("closure")} description={t("closureHelp")} className="danger-zone panel-flow">
      {asked ? <p role="status">{t("exportAsked")}</p> : null}
      <ActionForm label={t("askExport")} submit={t("askExport")} mutation={a.askExport} onSubmit={(v, done) => a.askExport.mutate(v.reason, { onSuccess: () => { setAsked(true); done(); } })} />
      {!org.closure ? <ActionForm label={t("startClosure")} submit={t("startClosure")} danger confirmName={org.name} mutation={a.startClosure}
          onSubmit={(v, done) => a.startClosure.mutate({ confirm_name: v.confirm_name, reason: v.reason }, { onSuccess: done })} />
        : org.closure.origin === "operator" ? <>
          <p>{t("closingSince", { date: day(org.closure.requested_at), erase: day(org.closure.erase_after) })}</p>
          <ActionForm label={t("cancelClosure")} submit={t("cancelClosure")} mutation={a.cancelClosure} onSubmit={(v, done) => a.cancelClosure.mutate(v.reason, { onSuccess: done })} />
        </>
        : <p className="text-muted">{t("closedByOwner", { erase: day(org.closure.erase_after) })}</p>}
    </Panel>
    <Panel title={t("erasure")} description={t("erasureHelp")} className="danger-zone panel-flow">
      {org.erasure ? <p><Badge state={ERASURE[org.erasure.state]}>{t(`erasureStates.${org.erasure.state}`)}</Badge></p> : null}
      {!org.closure && !erasure ? <p className="text-muted">{t("needsClosure")}</p>
        : !erasure ? <ActionForm label={t("requestErasure")} submit={t("requestErasure")} danger confirmName={org.name} mutation={a.requestErasure}
          onSubmit={(v, done) => a.requestErasure.mutate({ confirm_name: v.confirm_name, reason: v.reason }, { onSuccess: done })} />
        : erasure.state === "executed" ? <p>{t("executed", { receipt: erasure.receipt_id ?? "" })}</p>
        : <>
          {erasure.state === "pending" ? <>
            <p className="text-muted">{t(erasure.requested_by_me ? "requestedByMe" : "requestedByOther", { date: day(erasure.requested_at) })}</p>
            <ActionForm label={t("approveErasure")} submit={t("approveErasure")} danger confirmName={org.name} mutation={a.approveErasure}
              onSubmit={(v, done) => a.approveErasure.mutate({ erasure: erasure.id, confirm_name: v.confirm_name, reason: v.reason }, { onSuccess: done })} />
          </> : <p>{t("approved", { erase: org.closure ? day(org.closure.erase_after) : "" })}</p>}
          <ActionForm label={t("cancelErasure")} submit={t("cancelErasure")} mutation={a.cancelErasure}
            onSubmit={(v, done) => a.cancelErasure.mutate({ erasure: erasure.id, reason: v.reason }, { onSuccess: done })} />
        </>}
    </Panel>
  </div>;
}
