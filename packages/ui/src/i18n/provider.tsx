"use client";

import { type AbstractIntlMessages, NextIntlClientProvider } from "next-intl";
import { type ReactNode, useEffect, useSyncExternalStore } from "react";
import { DEFAULT_LOCALE, type Locale, localeCookie, preferredLocale } from "./locale";

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const readCookie = (): Locale => preferredLocale(document.cookie, navigator.languages ?? []);
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

/** Each app passes its own messages, Spanish first (AGENTS.md, i18n). */
export function I18nProvider({ messages, children }: { messages: Record<Locale, AbstractIntlMessages>; children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, readCookie, prerendered);
  const timeZone = useSyncExternalStore(noSubscription, browserTimeZone, prerenderedTimeZone);
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return (
    <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone={timeZone}>
      {children}
    </NextIntlClientProvider>
  );
}
