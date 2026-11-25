import type { Locale } from "./i18n/locale";

export const LOGOUT_URL = "/auth/logout";

/** Sign-in through the API's BFF (web-shell spec; the operator API's is the same, ADR-017). The API re-checks return_to; this only avoids sending junk. */
export function loginUrl(locale: Locale, returnTo: string): string {
  const params = new URLSearchParams({ lang: locale });
  if (returnTo.startsWith("/") && !returnTo.startsWith("//") && !returnTo.includes("\\")) {
    params.set("return_to", returnTo);
  }
  return `/auth/login?${params}`;
}
