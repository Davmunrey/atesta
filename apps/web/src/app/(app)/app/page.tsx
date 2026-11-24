"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMe } from "@/components/auth-gate";
import { CreateOrgForm } from "@/components/create-org-form";
import { Portfolio } from "@/components/portfolio";

/** First login without memberships lands on the create form; otherwise, the portfolio. */
export default function AppHome() {
  const t = useTranslations();
  const { memberships } = useMe();
  if (memberships.length === 0) return <CreateOrgForm />;
  return <Portfolio memberships={memberships}
    actions={<Link href="/app/new" className="dashboard-button action-link">{t("home.createAnother")}</Link>} />;
}
