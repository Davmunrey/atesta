"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { useUnsubscribe } from "@/lib/api/notifications";
import { ErrorMessage } from "./error-message";
import { LinkProblem } from "./public-header";

const KEY = "atesta_unsubscribe:v1";

function tabStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** The token arrives in the fragment (never sent to a server), leaves the address bar at once and
 * stays only in this tab, like the training link. Opening the page changes nothing. */
export function captureUnsubscribeToken(): string | null {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  if (token) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    try {
      tabStorage()?.setItem(KEY, token);
    } catch {
      // Storage disabled: the token still works for this page view.
    }
    return token;
  }
  try {
    return tabStorage()?.getItem(KEY) ?? null;
  } catch {
    return null;
  }
}

export function UnsubscribeConfirm() {
  const t = useTranslations("unsubscribe");
  const kinds = useTranslations("notifications.kinds");
  const [token, setToken] = useState<string | null | undefined>(undefined);
  // Browser-only state (the fragment), read once after hydration.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setToken(captureUnsubscribeToken()), []);
  const unsubscribe = useUnsubscribe();
  if (token === undefined) return <p role="status">{t("loading")}</p>;
  if (token === null) return <LinkProblem title={t("title")}>{t("missing")}</LinkProblem>;
  if (unsubscribe.isSuccess) {
    return <section className="grid gap-4"><h1 className="page-title">{t("title")}</h1>
      <p role="status">{t("done", { kind: kinds(`${unsubscribe.data.kind}.name`) })}</p>
      <p className="text-muted">{t("again")}</p></section>;
  }
  return <section className="grid gap-4">
    <h1 className="page-title">{t("title")}</h1>
    <p>{t("body")}</p>
    <div><button type="button" className="button-primary" disabled={unsubscribe.isPending} onClick={() => unsubscribe.mutate(token)}>{t("confirm")}</button></div>
    {unsubscribe.isError ? <ErrorMessage error={unsubscribe.error} /> : null}
  </section>;
}
