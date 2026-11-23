"use client";

import { useFormatter, useTranslations } from "next-intl";
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
  return <section className="flex flex-col gap-8">
    <h1 className="page-title">{t("title", { org: org.organization_name })}</h1>

    <section aria-labelledby={`${id}-export`} className="flex flex-col gap-2">
      <h2 id={`${id}-export`} className="text-lg font-semibold">{t("exportTitle")}</h2>
      <p className="text-muted">{t("exportHelp")}</p>
      <p><a className="dashboard-button" href={`/api/v1/orgs/${encodeURIComponent(org.organization_id)}/export`} download>{t("exportAction")}</a></p>
    </section>

    <section aria-labelledby={`${id}-close`} className="danger-zone flex flex-col gap-2">
      <h2 id={`${id}-close`} className="text-lg font-semibold">{t("closeTitle")}</h2>
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
    </section>
  </section>;
}
