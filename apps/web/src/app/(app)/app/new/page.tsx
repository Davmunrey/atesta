"use client";

import { useTranslations } from "next-intl";
import { CreateOrgForm } from "@/components/create-org-form";

export default function NewOrg() {
  const t = useTranslations("home");
  return <CreateOrgForm crumbs={[{ label: t("title"), href: "/app" }, { label: t("createAnother") }]} />;
}
