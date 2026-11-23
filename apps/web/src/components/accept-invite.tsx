"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { isLocale } from "@/i18n/locale";
import { ApiError, useAcceptInvitation, useMeQuery } from "@/lib/api/hooks";
import { loginUrl } from "@/lib/auth";
import { captureInviteToken, forgetInviteToken } from "@/lib/invite";
import { goTo } from "@/lib/navigation";
import { orgHome } from "@/lib/org";
import { ErrorMessage } from "./error-message";
import { LinkProblem } from "./public-header";

// A different account might still accept these; anything else means the token is spent.
const RETRYABLE = new Set(["identity.email_mismatch", "identity.email_unverified", "auth.invalid_token"]);

export function AcceptInvite() {
  const t = useTranslations("invite");
  const locale = useLocale();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const me = useMeQuery();
  const accept = useAcceptInvitation();
  const signedOut = me.error instanceof ApiError && me.error.status === 401;

  // Browser-only state (fragment, sessionStorage), read once after hydration.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setToken(captureInviteToken()), []);

  useEffect(() => {
    if (token && signedOut) goTo(loginUrl(isLocale(locale) ? locale : "es", "/invite"));
  }, [token, signedOut, locale]);

  function onAccept(value: string) {
    accept.mutate(value, {
      onSuccess: (result) => {
        forgetInviteToken();
        goTo(orgHome(result.organization_id));
      },
      onError: (error) => {
        if (!(error instanceof ApiError && error.code !== null && RETRYABLE.has(error.code))) forgetInviteToken();
      },
    });
  }

  if (token === null) return <LinkProblem title={t("unavailable")}>{t("missing")}</LinkProblem>;
  if (token === undefined || me.isPending || signedOut) return <p role="status">{t("loading")}</p>;
  if (me.isError) return <ErrorMessage error={me.error} />;
  return (
    <section className="flex flex-col gap-4">
      <h1 className="page-title">{t("title")}</h1>
      <p className="text-muted">{t("signedInAs", { email: me.data.email })}</p>
      {accept.isError ? <ErrorMessage error={accept.error} /> : null}
      <button
        type="button"
        disabled={accept.isPending}
        onClick={() => onAccept(token)}
        className="self-start rounded-md bg-accent px-4 py-2 font-medium text-accent-fg"
      >
        {t("accept")}
      </button>
    </section>
  );
}
