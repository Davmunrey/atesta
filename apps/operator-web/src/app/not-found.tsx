"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { PageHeader } from "@atesta/ui/page-frame";

/** Replaces Next's default 404, whose inline styles the CSP (style-src 'self') would block. */
export default function NotFound() {
  const t = useTranslations("portal.notFound");
  return <>
    <PageHeader title={t("title")} />
    <Link href="/" className="dashboard-button action-link">{t("back")}</Link>
  </>;
}
