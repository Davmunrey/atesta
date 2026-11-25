"use client";

import { useLocale, useTranslations } from "next-intl";
import { Empty, LoadError, Loading, Panel } from "@atesta/ui/page-frame";
import { ApiError } from "@atesta/ui/api-error";
import { Fact, Facts } from "@atesta/ui/facts";
import { useBillingProfile } from "@/lib/api/hooks";
import { legalEntity } from "@/content/legal-entity";

/** The billing details Atesta recorded (operator-portal spec): owners read them, never edit them. */
export function BillingDetails({ orgId }: { orgId: string }) {
  const t = useTranslations("settings.billing");
  const locale = useLocale();
  const query = useBillingProfile(orgId);
  const missing = query.error instanceof ApiError && query.error.code === "billing.no_profile";
  const country = (code: string) => new Intl.DisplayNames([locale], { type: "region" }).of(code) ?? code;
  const row = (label: string, value: string | null | undefined) =>
    <Fact key={label} label={label}>{value || t("notRecorded")}</Fact>;
  return <Panel title={t("title")} description={t("help", { email: legalEntity.email })} className="panel-flow">
    {query.isPending ? <Loading label={t("loading")} />
      : missing ? <Empty>{t("empty")}</Empty>
      : query.isError ? <LoadError error={query.error} onRetry={() => void query.refetch()} />
      : <Facts>
        {row(t("legalName"), query.data.legal_name)}
        {row(t("taxId"), query.data.tax_id)}
        {row(t("address"), [query.data.address_line1, query.data.address_line2].filter(Boolean).join(", "))}
        {row(t("postalCode"), query.data.postal_code)}
        {row(t("city"), query.data.city)}
        {row(t("region"), query.data.region)}
        {row(t("country"), query.data.country ? country(query.data.country) : null)}
        {row(t("contactEmail"), query.data.contact_email)}
      </Facts>}
  </Panel>;
}
