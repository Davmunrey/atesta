"use client";

import { useLocale, useTranslations } from "next-intl";
import { LocaleSwitcher } from "@/components/locale-switcher";

export default function Landing() {
  const t = useTranslations("landing");
  const locale = useLocale();
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-6 px-6">
      <LocaleSwitcher />
      <h1 className="text-4xl font-semibold tracking-tight">Atesta</h1>
      <p className="max-w-prose text-lg text-muted">{t("summary")}</p>
      <a
        href={`/auth/login?lang=${locale}`}
        className="self-start rounded-md bg-accent px-4 py-2 font-medium text-accent-fg"
      >
        {t("signIn")}
      </a>
    </main>
  );
}
