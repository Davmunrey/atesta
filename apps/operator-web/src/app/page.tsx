"use client";

import { useTranslations } from "next-intl";
import { PageHeader } from "@atesta/ui/page-frame";

/** Screen 2 of the operator-portal spec: the organization list (issue 488). */
export default function OrganizationsPage() {
  const t = useTranslations("organizations");
  return <PageHeader title={t("title")} description={t("description")} />;
}
