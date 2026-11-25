"use client";

import { useTranslations } from "next-intl";
import { OrganizationPage } from "@/components/organization-page";
import { PlanEditor } from "@/components/plan-editor";
import { canBill } from "@/lib/roles";

export default function PlanPage() {
  const t = useTranslations("plan");
  return <OrganizationPage title={t("title")} allowed={canBill}>{(org) => <PlanEditor org={org} />}</OrganizationPage>;
}
