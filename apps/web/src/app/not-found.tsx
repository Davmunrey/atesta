"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

/** Replaces Next's default 404, whose inline styles the CSP (style-src 'self') would block. */
export default function NotFound() {
  const t = useTranslations("notFound");
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-4 px-6">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <Link href="/" className="underline">
        {t("home")}
      </Link>
    </main>
  );
}
