"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";
import { useCreateOrg } from "@/lib/api/hooks";
import { goTo } from "@/lib/navigation";
import { orgHome } from "@/lib/org";
import { ErrorMessage } from "./error-message";
import { type Crumb, PageHeader, Panel } from "./page-frame";

/** The new-organization form, on the console page grid (console-unification spec). */
export function CreateOrgForm({ crumbs }: { crumbs?: Crumb[] }) {
  const t = useTranslations("createOrg");
  const create = useCreateOrg();
  const nameId = useId();

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    create.mutate(name, { onSuccess: (org) => goTo(orgHome(org.id)) });
  }

  return <>
    <PageHeader crumbs={crumbs} title={t("title")} description={t("help")} />
    <Panel>
      <form onSubmit={onSubmit} className="routine-form">
        <span><label htmlFor={nameId}>{t("name")}</label>
          <input id={nameId} name="name" required maxLength={200} autoComplete="organization" /></span>
        {create.isError ? <ErrorMessage error={create.error} /> : null}
        <div className="form-actions"><button type="submit" disabled={create.isPending} className="button-primary">{t("submit")}</button></div>
      </form>
    </Panel>
  </>;
}
