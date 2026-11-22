"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { LOGOUT_URL } from "@/lib/auth";
import { useMe } from "./auth-gate";
import { LocaleSwitcher } from "./locale-switcher";

export function AppHeader() {
  const t = useTranslations();
  return (
    <header className="app-header">
      <a href="#main-content" className="skip-link">{t("app.skipContent")}</a>
      <div className="app-header-inner">
        <Link href="/app" className="brand-mark">
          {t("brand.name")}
        </Link>
        <div className="header-actions">
          <LocaleSwitcher />
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}

/**
 * The account stays out of the way: one button, and a popover with who is signed in and how to
 * leave. A short list reached with Tab, so a popover without menu roles (modern-web-guidance,
 * menu: "A short list of links users Tab through is navigation"). popover/popovertarget are
 * Baseline Widely available and give light dismiss, Esc and focus return; anchor positioning is
 * only an enhancement in CSS.
 */
function AccountMenu() {
  const t = useTranslations("app");
  const me = useMe();
  const id = useId();
  const initial = (me.email.trim()[0] ?? "?").toLocaleUpperCase();
  return <>
    <button type="button" className="account-trigger" popoverTarget={id} aria-label={t("account")} title={me.email}>
      <span aria-hidden="true">{initial}</span>
    </button>
    <div id={id} popover="auto" className="account-menu" aria-label={t("account")}>
      <p className="account-email"><span className="text-muted">{t("signedInLabel")}</span> <strong>{me.email}</strong></p>
      <a href={LOGOUT_URL} className="account-signout">{t("signOut")}</a>
    </div>
  </>;
}
