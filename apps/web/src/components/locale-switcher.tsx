"use client";

import { useLocale, useTranslations } from "next-intl";
import { LOCALES } from "@/i18n/locale";
import { setLocale } from "@/i18n/provider";

export function LocaleSwitcher() {
  const t = useTranslations("locale");
  const current = useLocale();
  return (
    <nav aria-label={t("label")} className="flex gap-2 text-sm">
      {LOCALES.map((locale) => (
        <button
          key={locale}
          type="button"
          lang={locale}
          aria-pressed={locale === current}
          onClick={() => setLocale(locale)}
          className="rounded-sm px-2 py-1 text-muted aria-pressed:font-semibold aria-pressed:text-fg"
        >
          {t(locale)}
        </button>
      ))}
    </nav>
  );
}
