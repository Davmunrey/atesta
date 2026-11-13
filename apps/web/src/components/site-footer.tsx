"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

export function SiteFooter() {
  const t = useTranslations();
  return (
    <footer className="site-footer">
      <span>{t("brand.name")}</span>
      <nav aria-label={t("footer.label")}>
        <Link href="/cookies" className="underline">{t("cookies.title")}</Link>
      </nav>
    </footer>
  );
}
