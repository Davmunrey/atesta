export const LOCALES = ["es", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "es";
export const LOCALE_COOKIE = "atesta_locale";
const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export function isLocale(value: unknown): value is Locale {
  return LOCALES.includes(value as Locale);
}

/** The user's choice from a `document.cookie` string; Spanish when absent or unknown. */
export function localeFromCookie(cookie: string): Locale {
  for (const part of cookie.split(";")) {
    const [name, value] = part.trim().split("=", 2);
    if (name === LOCALE_COOKIE && isLocale(value)) return value;
  }
  return DEFAULT_LOCALE;
}

/** Not HttpOnly on purpose: the static app reads it in the browser. It holds no secret. */
export function localeCookie(locale: Locale): string {
  return `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=${ONE_YEAR_SECONDS}; SameSite=Lax; Secure`;
}
