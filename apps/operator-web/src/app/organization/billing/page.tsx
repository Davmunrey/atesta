"use client";

import { useTranslations } from "next-intl";
import { BillingForm } from "@/components/billing-form";
import { OrganizationPage } from "@/components/organization-page";
import { canBill } from "@/lib/roles";

export default function BillingPage() {
  const t = useTranslations("billingForm");
  return <OrganizationPage title={t("title")} allowed={canBill}>{(org) => <BillingForm org={org} />}</OrganizationPage>;
}
