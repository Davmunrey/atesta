"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { LOGOUT_URL } from "@/lib/auth";
import { useMe } from "./auth-gate";
import { LocaleSwitcher } from "./locale-switcher";

export function AppHeader() {
  const t = useTranslations();
  const me = useMe();
  return (
    <header className="app-header">
      <a href="#main-content" className="skip-link">{t("app.skipContent")}</a>
      <div className="app-header-inner">
        <Link href="/app" className="brand-mark">
          {t("brand.name")}
        </Link>
        <span className="session-label">{t("app.signedInAs", { email: me.email })}</span>
        <div className="header-actions">
          <LocaleSwitcher />
          <a href={LOGOUT_URL} className="text-sm underline">{t("app.signOut")}</a>
        </div>
      </div>
    </header>
  );
}
