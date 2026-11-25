"use client";

import { useLocale, useTranslations } from "next-intl";
import { type ReactNode, createContext, use, useEffect } from "react";
import { isLocale } from "@atesta/ui/i18n/locale";
import { ApiError } from "@atesta/ui/api-error";
import { useMeQuery } from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { loginUrl } from "@atesta/ui/auth";
import { goTo } from "@/lib/navigation";
import { ErrorMessage } from "@atesta/ui/error-message";

type Me = components["schemas"]["MeOut"];
const MeContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = use(MeContext);
  if (me === null) throw new Error("useMe outside AuthGate");
  return me;
}

/** GET /api/v1/me decides signed-in state (web-shell spec); 401 goes to sign-in and back. */
export function AuthGate({ children }: { children: ReactNode }) {
  const t = useTranslations("app");
  const locale = useLocale();
  const me = useMeQuery();
  const signedOut = me.error instanceof ApiError && me.error.status === 401;

  useEffect(() => {
    if (signedOut) {
      goTo(loginUrl(isLocale(locale) ? locale : "es", window.location.pathname + window.location.search));
    }
  }, [signedOut, locale]);

  if (me.data) return <MeContext value={me.data}>{children}</MeContext>;
  if (me.error && !signedOut) return <ErrorMessage error={me.error} />;
  return <p role="status">{t("loading")}</p>;
}
