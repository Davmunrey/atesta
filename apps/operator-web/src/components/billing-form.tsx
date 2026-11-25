"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { ApiError } from "@atesta/ui/api-error";
import { ErrorMessage } from "@atesta/ui/error-message";
import { FormField } from "@atesta/ui/form";
import { Panel } from "@atesta/ui/page-frame";
import { BILLING_FIELDS, type BillingField, useSetBilling } from "@/lib/api/billing";
import type { OrganizationDetail } from "@/lib/api/organizations";

const LIMITS: Record<BillingField, number> = { legal_name: 200, tax_id: 50, address_line1: 200, address_line2: 200, postal_code: 20, city: 100, region: 100, country: 2, contact_email: 254 };
const WIDE = new Set<BillingField>(["legal_name", "address_line1", "address_line2"]);

/** Screen 5 of the operator-portal spec: the details invoices use, and the internal reason. The
 *  API checks the formats (Spanish tax IDs from their official texts); a refused field is marked. */
export function BillingForm({ org }: { org: OrganizationDetail }) {
  const t = useTranslations("billingForm");
  const router = useRouter();
  const save = useSetBilling(org.id);
  const base = useId();
  const current = org.billing?.view === "full" ? org.billing : null;
  const [values, setValues] = useState<Record<BillingField, string>>(() =>
    Object.fromEntries(BILLING_FIELDS.map((f) => [f, current?.[f] ?? ""])) as Record<BillingField, string>);
  const [reason, setReason] = useState("");
  const refused = save.error instanceof ApiError && save.error.code === "operator.invalid_field" ? save.error.field : null;
  function submit() {
    const body = Object.fromEntries(BILLING_FIELDS.map((f) => [f, values[f].trim() || null]));
    save.mutate({ ...body, reason: reason.trim() }, {
      onSuccess: () => router.push(`/organization?id=${org.id}`),
      onError: (error) => { if (error instanceof ApiError && error.field) document.getElementById(`${base}-${error.field}`)?.focus(); },
    });
  }
  return <Panel title={t("form")} description={t("help")}>
    <form className="form-grid" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      {BILLING_FIELDS.map((f) => {
        const id = `${base}-${f}`;
        return <FormField key={f} id={id} label={t(`fields.${f}`)} wide={WIDE.has(f)} hint={t.has(`hints.${f}`) ? t(`hints.${f}`) : undefined}
          error={refused === f ? t("invalid") : undefined}>
          <input id={id} className="field" value={values[f]} maxLength={LIMITS[f]} required={f !== "address_line2"}
            type={f === "contact_email" ? "email" : "text"} autoComplete="off" aria-invalid={refused === f || undefined}
            aria-describedby={refused === f || t.has(`hints.${f}`) ? `${id}-hint` : undefined}
            onChange={(e) => setValues({ ...values, [f]: f === "country" ? e.target.value.toUpperCase() : e.target.value })} />
        </FormField>;
      })}
      <FormField id={`${base}-reason`} label={t("reason")} hint={t("reasonHint")} wide>
        <textarea id={`${base}-reason`} className="field" required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} aria-describedby={`${base}-reason-hint`} />
      </FormField>
      {save.isError ? <ErrorMessage error={save.error} /> : null}
      <div className="form-actions"><button type="submit" className="button-primary" disabled={save.isPending || !reason.trim()}>{t("save")}</button></div>
    </form>
  </Panel>;
}
