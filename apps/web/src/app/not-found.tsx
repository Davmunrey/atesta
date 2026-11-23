"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { PublicHeader } from "@/components/public-header";
import { SiteFooter } from "@/components/site-footer";

/** Replaces Next's default 404, whose inline styles the CSP (style-src 'self') would block. */
export default function NotFound() {
  const t = useTranslations("notFound");
  return (
    <div className="public-surface flex min-h-dvh flex-col bg-bg text-fg">
    <PublicHeader />
    <main id="content" tabIndex={-1} className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-4 px-6 py-12">
      <h1 className="page-title">{t("title")}</h1>
      <Link href="/" className="action-link self-start underline">
        {t("home")}
      </Link>
    </main>
    <SiteFooter />
    </div>
  );
}
