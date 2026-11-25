"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId, useState } from "react";
import { Notice } from "@atesta/ui/app-shell";
import { ErrorMessage } from "@atesta/ui/error-message";
import { Fact, Facts } from "@atesta/ui/facts";
import { FormField } from "@atesta/ui/form";
import { LoadError, Loading, Panel } from "@atesta/ui/page-frame";
import { type PlanInfo, usePlans, useSetPlan } from "@/lib/api/billing";
import type { OrganizationDetail } from "@/lib/api/organizations";
import { AddonName } from "./organization-labels";

/** Screen 4 of the operator-portal spec: plan, add-ons, the customer-visible note and the internal
 *  reason, with what the change does before it is saved. */
export function PlanEditor({ org }: { org: OrganizationDetail }) {
  const t = useTranslations("plan");
  const plans = usePlans();
  const router = useRouter();
  const save = useSetPlan(org.id);
  const ids = { plan: useId(), note: useId(), reason: useId() };
  const [plan, setPlan] = useState<string>(org.plan.plan);
  const [addons, setAddons] = useState(new Set(org.plan.addons ?? []));
  const [note, setNote] = useState(org.plan.note ?? "");
  const [reason, setReason] = useState("");
  if (plans.isPending) return <Loading />;
  if (plans.isError) return <LoadError error={plans.error} onRetry={() => void plans.refetch()} />;
  const before = plans.data.plans.find((p) => p.plan === org.plan.plan);
  const after = plans.data.plans.find((p) => p.plan === plan);
  const toggle = (addon: string) => setAddons((set) => { const next = new Set(set); if (next.has(addon)) next.delete(addon); else next.add(addon); return next; });
  return <div className="panel-grid panel-grid-main">
    <Panel title={t("form")}>
      <form className="form-grid" onSubmit={(e) => { e.preventDefault();
        save.mutate({ plan, addons: [...addons].sort(), note: note.trim(), reason: reason.trim() }, { onSuccess: () => router.push(`/organization?id=${org.id}`) }); }}>
        <FormField id={ids.plan} label={t("plan")}>
          <select id={ids.plan} className="field" value={plan} onChange={(e) => setPlan(e.target.value)}>
            {plans.data.plans.map((p) => <option key={p.plan} value={p.plan}>{t(`plans.${p.plan}`)}</option>)}</select>
        </FormField>
        <fieldset><legend>{t("addons")}</legend>
          {plans.data.addons.map((addon) => <span key={addon} className="checkbox-row">
            <input id={`${ids.plan}-${addon}`} type="checkbox" checked={addons.has(addon)} onChange={() => toggle(addon)} />
            <label htmlFor={`${ids.plan}-${addon}`}><AddonName addon={addon} /></label></span>)}
        </fieldset>
        <FormField id={ids.note} label={t("note")} hint={t("noteHint")} wide>
          <textarea id={ids.note} className="field" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} aria-describedby={`${ids.note}-hint`} />
        </FormField>
        <FormField id={ids.reason} label={t("reason")} hint={t("reasonHint")} wide>
          <textarea id={ids.reason} className="field" required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} aria-describedby={`${ids.reason}-hint`} />
        </FormField>
        {save.isError ? <ErrorMessage error={save.error} /> : null}
        <div className="form-actions"><button type="submit" className="button-primary" disabled={save.isPending || !reason.trim()}>{t("save")}</button></div>
      </form>
    </Panel>
    <Panel title={t("preview")} className="panel-flow"><Preview org={org} before={before} after={after} /></Panel>
  </div>;
}

/** What the change does: the connector limit and the features gained or lost (spec, screen 4). */
function Preview({ org, before, after }: { org: OrganizationDetail; before?: PlanInfo; after?: PlanInfo }) {
  const t = useTranslations("plan");
  const f = useTranslations("plan.features");
  if (!before || !after) return null;
  const limit = (n: number | null) => n === null ? t("noLimit") : t("connections", { count: n });
  const gained = after.features.filter((x) => !before.features.includes(x));
  const lost = before.features.filter((x) => !after.features.includes(x));
  const over = after.connector_limit !== null && org.connections.in_use > after.connector_limit;
  return <>
    <Facts>
      <Fact label={t("connectorLimit")}>{before.plan === after.plan ? limit(after.connector_limit) : `${limit(before.connector_limit)} → ${limit(after.connector_limit)}`}</Fact>
      <Fact label={t("gains")}>{gained.length ? gained.map((x) => f(x)).join(", ") : t("nothing")}</Fact>
      <Fact label={t("loses")}>{lost.length ? lost.map((x) => f(x)).join(", ") : t("nothing")}</Fact>
    </Facts>
    {over ? <Notice>{t("overLimit", { count: org.connections.in_use, limit: after.connector_limit ?? 0 })}</Notice> : null}
  </>;
}
