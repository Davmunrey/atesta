"use client";

import { useLocale, useTranslations } from "next-intl";

export default function Landing() {
  const t = useTranslations();
  const locale = useLocale();
  return (
    <main id="content" tabIndex={-1} className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-6 py-12">
      <h1 className="page-title">{t("brand.name")}</h1>
      <p className="max-w-prose text-lg text-muted">{t("landing.summary")}</p>
      <a
        href={`/auth/login?lang=${locale}`}
        className="action-link self-start rounded-md bg-accent px-4 py-2 font-medium text-accent-fg"
      >
        {t("landing.signIn")}
      </a>
    </main>
  );
}
