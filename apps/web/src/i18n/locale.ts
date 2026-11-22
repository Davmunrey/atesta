export const LOCALES = ["es", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "es";
export const LOCALE_COOKIE = "atesta_locale";
export const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export function isLocale(value: unknown): value is Locale {
  return LOCALES.includes(value as Locale);
}

/** The user's choice from a `document.cookie` string; Spanish when absent or unknown. */
export function localeFromCookie(cookie: string): Locale {
  return storedLocale(cookie) ?? DEFAULT_LOCALE;
}

/** The stored choice, or null when the person has not chosen yet. */
function storedLocale(cookie: string): Locale | null {
  for (const part of cookie.split(";")) {
    const [name, value] = part.trim().split("=", 2);
    if (name === LOCALE_COOKIE && isLocale(value)) return value;
  }
  return null;
}

/** An explicit choice wins; a first visit follows the browser's first supported language. */
export function preferredLocale(cookie: string, languages: readonly string[]): Locale {
  const stored = storedLocale(cookie);
  if (stored) return stored;
  for (const language of languages) {
    const base = language.toLowerCase().split("-")[0];
    if (isLocale(base)) return base;
  }
  return DEFAULT_LOCALE;
}

/** Not HttpOnly on purpose: the static app reads it in the browser. It holds no secret. */
export function localeCookie(locale: Locale): string {
  return `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=${ONE_YEAR_SECONDS}; SameSite=Lax; Secure`;
}
