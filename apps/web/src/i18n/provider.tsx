"use client";

import { NextIntlClientProvider } from "next-intl";
import { type ReactNode, useEffect, useSyncExternalStore } from "react";
import en from "../../messages/en.json";
import es from "../../messages/es.json";
import { DEFAULT_LOCALE, type Locale, localeCookie, localeFromCookie } from "./locale";

const MESSAGES = { es, en } as const;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const readCookie = (): Locale => localeFromCookie(document.cookie);
// The export is prerendered in Spanish and UTC; React re-renders after hydration with the
// cookie's locale and the browser's time zone.
const prerendered = (): Locale => DEFAULT_LOCALE;
const noSubscription = () => () => {};
const browserTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
const prerenderedTimeZone = () => "UTC";

export function setLocale(locale: Locale): void {
  document.cookie = localeCookie(locale);
  for (const listener of listeners) listener();
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, readCookie, prerendered);
  const timeZone = useSyncExternalStore(noSubscription, browserTimeZone, prerenderedTimeZone);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return (
    <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone={timeZone}>
      {children}
    </NextIntlClientProvider>
  );
}
