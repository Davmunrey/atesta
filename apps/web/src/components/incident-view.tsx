"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { type FormEvent, useId } from "react";
import { type IncidentClock, useIncident, useIncidentUpdate } from "@/lib/api/routines";
import { type Membership, orgHome, orgIncidents } from "@/lib/org";
import { isContributor } from "@/lib/permissions";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { PageHeader, Panel } from "./page-frame";

/** One incident: its reporting deadlines from pack content, its entries, and closing it. */
export function IncidentView({ org, incidentId }: { org: Membership; incidentId: string }) {
  const t = useTranslations("routines.incidents");
  const format = useFormatter();
  const locale = useLocale();
  const query = useIncident(org.organization_id, incidentId);
  const update = useIncidentUpdate(org.organization_id, incidentId);
  const noteId = useId();
  const crumbs = [{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title"), href: orgIncidents(org.organization_id) }];
  if (query.isPending) return <><PageHeader crumbs={crumbs} title={t("title")} /><p role="status">{t("loading")}</p></>;
  if (query.isError) return <><PageHeader crumbs={crumbs} title={t("title")} /><ErrorMessage error={query.error} /></>;
  const incident = query.data;
  const open = incident.closed_at === null;
  const canAct = open && isContributor(org.role);
  const time = (value: string) => format.dateTime(new Date(value), { dateStyle: "medium", timeStyle: "short" });
  const title = (c: IncidentClock) => (locale === "en" ? c.title_en : c.title_es);
  const byRef = new Map(incident.clocks.map((c) => [c.ref, c]));
  const flags = [incident.significant ? t("significant") : null, incident.personal_data ? t("personalData") : null].filter(Boolean).join(" · ");
  function addNote(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    update.mutate({ kind: "note", note: String(new FormData(form).get("note") ?? "") }, { onSuccess: () => form.reset() });
  }
  return <div className="panel-grid">
    <PageHeader crumbs={[...crumbs, { label: incident.title }]} title={incident.title}
      description={<>{t("aware")}: {time(incident.aware_at)} · {flags || t("noFlags")}</>}
      actions={canAct
        ? <button type="button" className="button-primary" disabled={update.isPending} onClick={() => update.mutate({ kind: "closed", note: "" })}>{t("close")}</button>
        : incident.closed_at ? <span className="badge" data-severity="done"><Icon name="done" />{t("closed")}</span> : null} />
    {update.isError ? <ErrorMessage error={update.error} /> : null}
    {update.isSuccess && !open ? <p role="status" className="notice"><Icon name="done" />{t("closedEvidence")}</p> : null}
    <Panel title={t("clocks")} description={t("clocksHelp")}>
      {incident.clocks.length === 0 ? <p className="text-muted">{t("noClocks")}</p>
        : <div className="table-region" role="region" aria-label={t("clocks")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("clock")}</th><th scope="col">{t("due")}</th><th scope="col">{t("status")}</th></tr></thead>
          <tbody>{incident.clocks.map((c) => <tr key={c.ref}>
            <td data-label={t("clock")}>{title(c)}<span className="block text-sm text-muted">{c.framework_name} · {c.requirement}</span></td>
            <td data-label={t("due")} className="tabular-nums">{c.due_at ? time(c.due_at) : "—"}</td>
            <td data-label={t("status")}><ClockStatus clock={c} time={time} />
              {canAct && (c.state === "running" || c.state === "overdue")
                ? <button type="button" className="dashboard-button clock-action" disabled={update.isPending}
                  onClick={() => update.mutate({ kind: "clock", clock: c.ref, note: "" })}>{t("sent")}<span className="sr-only">{t("sentWhich", { clock: title(c) })}</span></button> : null}</td>
          </tr>)}</tbody>
        </table></div>}
    </Panel>
    <Panel title={t("updates")}>
      {incident.updates.length === 0 ? <p className="text-muted">{t("noUpdates")}</p>
        : <ol className="update-list">{incident.updates.map((u) => <li key={`${u.recorded_at}:${u.kind}:${u.clock ?? ""}`}>
          <span className="text-sm text-muted tabular-nums">{time(u.recorded_at)}</span>
          <span>{u.kind === "clock" ? t("kind.clock", { clock: u.clock && byRef.has(u.clock) ? title(byRef.get(u.clock)!) : u.clock ?? "" }) : t(`kind.${u.kind}`)}
            {u.note ? <span className="block">{u.note}</span> : null}</span>
        </li>)}</ol>}
      {canAct ? <form onSubmit={addNote} className="routine-form">
        <span className="routine-form-wide"><label htmlFor={noteId}>{t("note")}</label><textarea id={noteId} name="note" rows={3} required maxLength={2000} /></span>
        <div className="form-actions"><button type="submit" className="dashboard-button" disabled={update.isPending}>{t("addNote")}</button></div>
      </form> : null}
    </Panel>
  </div>;
}

function ClockStatus({ clock, time }: { clock: IncidentClock; time: (value: string) => string }) {
  const t = useTranslations("routines.incidents");
  if (clock.state === "met" && clock.met_at) {
    return clock.late
      ? <span className="badge" data-severity="overdue"><Icon name="overdue" />{t("metLate", { time: time(clock.met_at) })}</span>
      : <span className="badge" data-severity="done"><Icon name="done" />{t("met", { time: time(clock.met_at) })}</span>;
  }
  if (clock.state === "overdue") return <span className="badge" data-severity="overdue"><Icon name="overdue" />{t("late")}</span>;
  if (clock.state === "running") return <span className="badge" data-severity="pending"><Icon name="pending" />{t("running")}</span>;
  return <span className="text-sm text-muted">{t("waiting")}</span>;
}
