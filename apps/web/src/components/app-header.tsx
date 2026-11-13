"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { LOGOUT_URL } from "@/lib/auth";
import { useMe } from "./auth-gate";
import { LocaleSwitcher } from "./locale-switcher";

export function AppHeader() {
  const t = useTranslations("app");
  const me = useMe();
  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-4 px-6 py-3">
        <Link href="/app" className="font-semibold">
          Atesta
        </Link>
        <span className="ml-auto text-sm text-muted">{t("signedInAs", { email: me.email })}</span>
        <LocaleSwitcher />
        <a href={LOGOUT_URL} className="text-sm underline">
          {t("signOut")}
        </a>
      </div>
    </header>
  );
}
