"use client";

import { useLocale, useTranslations } from "next-intl";
import { type ReactNode, useId, useState } from "react";
import { ApiError } from "@atesta/ui/api-error";
import { Notice } from "@atesta/ui/app-shell";
import { loginUrl } from "@atesta/ui/auth";
import { ErrorMessage } from "@atesta/ui/error-message";
import { FormField, TypedName } from "@atesta/ui/form";
import { isLocale } from "@atesta/ui/i18n/locale";
import { REASON_CODES, type ReasonCode } from "@/lib/api/actions";

export type ActionValues = { reason: string; confirm_name: string; reason_code: ReasonCode };
type Mutation = { isPending: boolean; error: unknown; reset: () => void };

/**
 * One admin action as DESIGN.md asks for destructive ones: a bordered button that opens the form
 * in place, then the action and "Cancelar". `confirmName` asks for the organization's exact name;
 * `codes` for a suspension reason code. Every action takes the internal reason.
 */
export function ActionForm({ label, submit, danger, confirmName, codes, mutation, onSubmit }: {
  label: string; submit: string; danger?: boolean; confirmName?: string; codes?: boolean; mutation: Mutation;
  onSubmit: (values: ActionValues, done: () => void) => void;
}) {
  const t = useTranslations("actions");
  const id = useId();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<ActionValues>({ reason: "", confirm_name: "", reason_code: "non_payment" });
  const close = () => { setOpen(false); setValues({ reason: "", confirm_name: "", reason_code: "non_payment" }); mutation.reset(); };
  if (!open) return <p><button type="button" className="dashboard-button" onClick={() => setOpen(true)}>{label}</button></p>;
  const ready = values.reason.trim() !== "" && (!confirmName || values.confirm_name === confirmName);
  return <form className="form-grid" aria-label={label}
    onSubmit={(e) => { e.preventDefault(); onSubmit({ ...values, reason: values.reason.trim() }, close); }}>
    {codes ? <FormField id={`${id}-code`} label={t("reasonCode")}>
      <select id={`${id}-code`} className="field" value={values.reason_code} onChange={(e) => setValues({ ...values, reason_code: e.target.value as ReasonCode })}>
        {REASON_CODES.map((c) => <option key={c} value={c}>{t(`codes.${c}`)}</option>)}</select>
    </FormField> : null}
    <FormField id={`${id}-reason`} label={t("reason")} hint={t("reasonHint")} wide>
      <textarea id={`${id}-reason`} className="field" required maxLength={500} value={values.reason} aria-describedby={`${id}-reason-hint`}
        onChange={(e) => setValues({ ...values, reason: e.target.value })} />
    </FormField>
    {confirmName ? <TypedName id={`${id}-name`} name={confirmName} value={values.confirm_name} onChange={(confirm_name) => setValues({ ...values, confirm_name })} /> : null}
    {mutation.error ? <ActionError error={mutation.error} /> : null}
    <div className="form-actions">
      <button type="submit" className={danger ? "button-danger" : "button-primary"} disabled={!ready || mutation.isPending}>{submit}</button>
      <button type="button" className="dashboard-button" onClick={close}>{t("cancel")}</button>
    </div>
  </form>;
}

/** A refusal; for an action that needs a recent sign-in, the way to sign in again and come back. */
export function ActionError({ error }: { error: unknown }): ReactNode {
  const t = useTranslations("actions");
  const locale = useLocale();
  if (!(error instanceof ApiError && error.code === "operator.recent_auth_required")) return <ErrorMessage error={error} />;
  const back = window.location.pathname + window.location.search;
  return <div role="alert" className="form-wide"><Notice severity="overdue">{t("recentAuth")}{" "}
    <a href={loginUrl(isLocale(locale) ? locale : "es", back)} className="text-link underline">{t("signInAgain")}</a></Notice></div>;
}
