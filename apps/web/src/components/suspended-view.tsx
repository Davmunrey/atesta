"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { PageHeader, Panel } from "@atesta/ui/page-frame";
import { legalEntity } from "@/content/legal-entity";
import { type Membership, orgSettings } from "@/lib/org";
import { BillingDetails } from "./billing-details";

/**
 * What a suspended organization shows on every page (operator-portal spec): nothing is deleted;
 * owners see the reason and keep export, closure and their billing details (GDPR art. 20).
 */
export function SuspendedView({ org }: { org: Membership }) {
  const t = useTranslations("suspended");
  const format = useFormatter();
  const since = org.suspended_at ? format.dateTime(new Date(org.suspended_at), { dateStyle: "long" }) : "";
  const body = t("body", { org: org.organization_name, date: since });
  if (org.role !== "owner") {
    return <div className="panel-grid">
      <PageHeader title={t("title")} description={<><p>{body}</p><p>{t("member")}</p></>} />
    </div>;
  }
  const reason = org.suspension_reason ?? "other";
  return <div className="panel-grid">
    <PageHeader title={t("title")} description={<p>{body}</p>} />
    <Panel className="panel-flow">
      <p>{t("owner", { reason: t(`reason.${reason}`), email: legalEntity.email })}</p>
      <p className="text-muted">{t("ownerActions")}</p>
      <p className="flex flex-wrap gap-3">
        <a className="dashboard-button action-link" href={`/api/v1/orgs/${encodeURIComponent(org.organization_id)}/export`} download>{t("export")}</a>
        <Link className="dashboard-button action-link" href={orgSettings(org.organization_id)}>{t("closure")}</Link>
      </p>
    </Panel>
    <BillingDetails orgId={org.organization_id} />
  </div>;
}
