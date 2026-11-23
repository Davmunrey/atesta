"use client";

import { useFormatter, useTranslations } from "next-intl";
import { PageHeader, Panel } from "./page-frame";
import { orgHome as homeOf } from "@/lib/org";
import { useId, useState } from "react";
import { useCancelClosure, useRequestClosure } from "@/lib/api/hooks";
import type { Membership } from "@/lib/org";
import { ErrorMessage } from "./error-message";

/** Owner settings (organization-closure spec): take the data, or close the organization. */
export function SettingsView({ org }: { org: Membership }) {
  const t = useTranslations("settings");
  const format = useFormatter();
  const id = useId();
  const request = useRequestClosure(org.organization_id);
  const cancel = useCancelClosure(org.organization_id);
  const [typed, setTyped] = useState("");
  if (org.role !== "owner") return <p className="text-muted">{t("ownersOnly")}</p>;
  const closing = org.closure_erase_after;
  const day = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "long" });
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: homeOf(org.organization_id) }, { label: t("crumb") }]} title={t("title", { org: org.organization_name })} />

    <Panel title={t("exportTitle")} className="panel-flow">
      <p className="text-muted">{t("exportHelp")}</p>
      <p><a className="dashboard-button action-link" href={`/api/v1/orgs/${encodeURIComponent(org.organization_id)}/export`} download>{t("exportAction")}</a></p>
    </Panel>

    <Panel title={t("closeTitle")} className="danger-zone panel-flow">
      {closing ? <>
        <p role="status">{t("closing", { date: day(closing) })}</p>
        {cancel.isError ? <ErrorMessage error={cancel.error} /> : null}
        <p><button type="button" className="dashboard-button" disabled={cancel.isPending} onClick={() => cancel.mutate()}>{t("cancelAction")}</button></p>
      </> : <>
        <p className="text-muted">{t("closeHelp")}</p>
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); request.mutate(typed); }}>
          <span className="flex flex-col gap-1">
            <label htmlFor={`${id}-name`}>{t("confirmLabel", { org: org.organization_name })}</label>
            <input id={`${id}-name`} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" className="rounded-md border border-border bg-bg px-3 py-2" />
          </span>
          <button type="submit" disabled={typed !== org.organization_name || request.isPending} className="rounded-md bg-danger px-4 py-2 font-medium text-danger-fg">{t("closeAction")}</button>
        </form>
        {request.isError ? <ErrorMessage error={request.error} /> : null}
      </>}
    </Panel>
  </div>;
}
