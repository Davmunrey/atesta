"use client";

import Link from "next/link";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { type FormEvent, useId } from "react";
import { type IncidentCriterion, useCreateIncident, useIncidentCriteria, useIncidents } from "@/lib/api/routines";
import { goTo } from "@/lib/navigation";
import { type Membership, orgHome, orgIncident } from "@/lib/org";
import { isContributor } from "@/lib/permissions";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { PageHeader, Panel } from "./page-frame";

/** The value of a datetime-local input for a moment, in the browser's time zone. */
export function localInput(at: Date): string {
  return new Date(at.getTime() - at.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

/** Incident register (recorded-routines spec): what happened, when you knew, and the deadlines. */
export function IncidentsView({ org }: { org: Membership }) {
  const t = useTranslations("routines.incidents");
  const format = useFormatter();
  const list = useIncidents(org.organization_id);
  const time = (value: string) => format.dateTime(new Date(value), { dateStyle: "medium", timeStyle: "short" });
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")} />
    {isContributor(org.role) ? <CreateIncident orgId={org.organization_id} /> : null}
    <Panel title={t("list")}>
      {list.isPending ? <p role="status">{t("loading")}</p> : list.isError ? <ErrorMessage error={list.error} />
        : list.data.length === 0 ? <p className="text-muted">{t("empty")}</p>
        : <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("incident")}</th><th scope="col">{t("aware")}</th><th scope="col">{t("state")}</th></tr></thead>
          <tbody>{list.data.map((i) => <tr key={i.id}>
            <td data-label={t("incident")}><Link href={orgIncident(org.organization_id, i.id)} className="text-link underline">{i.title}</Link></td>
            <td data-label={t("aware")} className="tabular-nums">{time(i.aware_at)}</td>
            <td data-label={t("state")}>{i.closed_at ? <span className="badge" data-severity="done"><Icon name="done" />{t("closed")}</span>
              : i.overdue > 0 ? <span className="badge" data-severity="overdue"><Icon name="overdue" />{t("overdue", { count: i.overdue })}</span>
              : i.next_due_at ? <span className="badge" data-severity="pending"><Icon name="pending" />{t("next", { time: time(i.next_due_at) })}</span>
              : <span className="text-muted">{t("noClocks")}</span>}</td>
          </tr>)}</tbody>
        </table></div>}
    </Panel>
  </div>;
}

function CreateIncident({ orgId }: { orgId: string }) {
  const t = useTranslations("routines.incidents");
  const create = useCreateIncident(orgId);
  const criteria = useIncidentCriteria(orgId).data ?? [];
  const ids = { title: useId(), aware: useId(), significant: useId(), help: useId(), personal: useId() };
  const now = localInput(new Date());
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    create.mutate({
      title: String(data.get("title") ?? ""),
      aware_at: new Date(String(data.get("aware_at") ?? "")).toISOString(),
      significant: data.get("significant") === "on",
      personal_data: data.get("personal_data") === "on",
    }, { onSuccess: (created) => goTo(orgIncident(orgId, created.id)) });
  }
  return <Panel title={t("create")} description={t("createHelp")}>
    <form onSubmit={submit} className="routine-form">
      <span><label htmlFor={ids.title}>{t("incidentTitle")}</label><input id={ids.title} name="title" required maxLength={200} /></span>
      <span><label htmlFor={ids.aware}>{t("awareAt")}</label><input id={ids.aware} name="aware_at" type="datetime-local" required defaultValue={now} max={now} /></span>
      <span className="routine-form-wide checkbox-row"><input id={ids.significant} name="significant" type="checkbox" aria-describedby={ids.help} />
        <label htmlFor={ids.significant}>{t("significant")}</label><span id={ids.help} className="text-sm text-muted">{t("significantHelp")}</span>
        <Criteria items={criteria.filter((c) => c.needs === "significant")} /></span>
      <span className="routine-form-wide checkbox-row"><input id={ids.personal} name="personal_data" type="checkbox" />
        <label htmlFor={ids.personal}>{t("personalData")}</label>
        <Criteria items={criteria.filter((c) => c.needs === "personal_data")} /></span>
      <div className="form-actions"><button type="submit" className="button-primary" disabled={create.isPending}>{t("record")}</button></div>
      {create.isError ? <ErrorMessage error={create.error} /> : null}
    </form>
  </Panel>;
}

/** The official text behind a flag, one disclosure per framework; never a verdict (ADR-005). */
function Criteria({ items }: { items: IncidentCriterion[] }) {
  const t = useTranslations("routines.incidents");
  const english = useLocale() === "en";
  if (items.length === 0) return null;
  return <span className="criteria">{items.map((c) => {
    const text = english && c.text_en ? c.text_en : c.text_es;
    const title = english && c.title_en ? c.title_en : c.title_es;
    const lang = english && c.text_en ? undefined : "es";
    return <details key={`${c.framework_key}:${c.requirement}`}>
      <summary>{t("criteria", { framework: c.framework_name, title })}</summary>
      <div lang={lang} className="criteria-text">{text.split("\n\n").map((p, i) => <p key={i}>{p}</p>)}</div>
      <a href={c.source} className="text-link underline text-sm" rel="noopener noreferrer" target="_blank">{t("criteriaSource")}</a>
    </details>;
  })}</span>;
}
