"use client";

import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useEffect, useId, useState } from "react";
import { ApiError } from "@/lib/api/hooks";
import { messageKey } from "@/lib/api/errors";
import { useAcknowledge, useTrainingLink } from "@/lib/api/routines";
import { ErrorMessage } from "./error-message";
import { LinkProblem } from "./public-header";
import { Icon } from "./icons";

export const TRAINING_KEY = "atesta_training:v1";

function tabStorage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * The public training page (recorded-routines spec). The token arrives in the URL fragment, so
 * servers and logs never see it. It is removed from the address bar at once, kept in this tab's
 * sessionStorage (a reload, or React running the effect twice, still finds it) and sent only in
 * request bodies. No account and no cookie are involved.
 */
export function captureTrainingToken(): string | null {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  if (token) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    try {
      tabStorage()?.setItem(TRAINING_KEY, token);
    } catch {
      // Storage disabled: the token still works for this page view.
    }
    return token;
  }
  try {
    return tabStorage()?.getItem(TRAINING_KEY) ?? null;
  } catch {
    return null;
  }
}

export function TrainingConfirm() {
  const t = useTranslations("trainingLink");
  const errors = useTranslations();
  const format = useFormatter();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  // Browser-only state (the fragment), read once after hydration.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setToken(captureTrainingToken()), []);
  const link = useTrainingLink(token ?? null);
  const acknowledge = useAcknowledge();
  const ids = { name: useId(), email: useId(), read: useId() };
  if (token === null) return <LinkProblem title={t("unavailable")}>{t("missing")}</LinkProblem>;
  if (token === undefined || link.isPending) return <p role="status">{t("loading")}</p>;
  if (link.isError) {
    // A refused link (4xx) is the link's problem, not a form error: a malformed token reads as invalid.
    const error = link.error;
    if (!(error instanceof ApiError) || error.status >= 500) return <ErrorMessage error={error} />;
    return <LinkProblem title={t("unavailable")}>{errors(messageKey(error.status === 422 ? "compliance.training_link_invalid" : error.code))}</LinkProblem>;
  }
  const campaign = link.data;
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    acknowledge.mutate({ token: token ?? "", full_name: String(data.get("full_name") ?? ""), email: String(data.get("email") ?? "") });
  }
  return <section className="flex flex-col gap-4">
    <h1 className="page-title">{campaign.title}</h1>
    <p className="text-muted">{t("intro")} {t("closes", { date: format.dateTime(new Date(`${campaign.closes_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) })}</p>
    <p><a href={campaign.material_url} className="text-link underline" rel="noopener noreferrer" target="_blank">{t("material")}</a></p>
    {acknowledge.isSuccess
      ? <p role="status" className="notice"><Icon name="done" />{acknowledge.data.recorded ? t("done") : t("already")}</p>
      : <form onSubmit={submit} className="routine-form" aria-label={t("heading")}>
        <span><label htmlFor={ids.name}>{t("name")}</label><input id={ids.name} name="full_name" required maxLength={200} autoComplete="name" /></span>
        <span><label htmlFor={ids.email}>{t("email")}</label><input id={ids.email} name="email" type="email" required maxLength={320} autoComplete="email" /></span>
        <span className="routine-form-wide checkbox-row"><input id={ids.read} type="checkbox" required /><label htmlFor={ids.read}>{t("read")}</label></span>
        <div className="form-actions"><button type="submit" className="button-primary" disabled={acknowledge.isPending}>{t("confirm")}</button></div>
        {acknowledge.isError ? <ErrorMessage error={acknowledge.error} /> : null}
      </form>}
  </section>;
}
