"use client";

import { useLocale, useTranslations } from "next-intl";
import { LOCALES } from "./i18n/locale";
import { setLocale } from "./i18n/provider";

/** compact: the console top bar shows "ES / EN" on ink; full names stay as accessible labels. */
export function LocaleSwitcher({ compact = false }: { compact?: boolean }) {
  const t = useTranslations("locale");
  const current = useLocale();
  if (compact) return <nav aria-label={t("label")} className="topbar-locale">
    {LOCALES.map((locale) => <button key={locale} type="button" lang={locale} aria-pressed={locale === current}
      title={t(locale)} onClick={() => setLocale(locale)}>{locale.toUpperCase()}<span className="sr-only"> ({t(locale)})</span></button>)}
  </nav>;
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
