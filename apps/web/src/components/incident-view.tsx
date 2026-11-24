"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { type IncidentClock, useIncident, useIncidentUpdate } from "@/lib/api/routines";
import { localInput } from "./incidents-view";
import { type Membership, orgHome, orgIncidents } from "@/lib/org";
import { isContributor } from "@/lib/permissions";
import { Badge, ClockBadge } from "./badge";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { LoadError, Loading, PageHeader, Panel } from "./page-frame";

/** One incident: its reporting deadlines from pack content, its entries, and closing it. */
export function IncidentView({ org, incidentId }: { org: Membership; incidentId: string }) {
  const t = useTranslations("routines.incidents");
  const format = useFormatter();
  const locale = useLocale();
  const query = useIncident(org.organization_id, incidentId);
  const update = useIncidentUpdate(org.organization_id, incidentId);
  const noteId = useId();
  const classifyId = useId();
  const [confirming, setConfirming] = useState(false);
  const crumbs = [{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title"), href: orgIncidents(org.organization_id) }];
  if (query.isPending) return <><PageHeader crumbs={crumbs} title={t("title")} /><Loading label={t("loading")} /></>;
  if (query.isError) return <><PageHeader crumbs={crumbs} title={t("title")} /><LoadError error={query.error} onRetry={() => void query.refetch()} /></>;
  const incident = query.data;
  const open = incident.closed_at === null;
  const canAct = open && isContributor(org.role);
  const time = (value: string) => format.dateTime(new Date(value), { dateStyle: "medium", timeStyle: "short" });
  const title = (c: IncidentClock) => (locale === "en" ? c.title_en : c.title_es);
  const byRef = new Map(incident.clocks.map((c) => [c.ref, c]));
  const unsent = incident.clocks.filter((c) => c.state !== "met").length;
  const close = () => update.mutate({ kind: "closed", note: "" }, { onSettled: () => setConfirming(false) });
  const flags = [incident.significant ? t("significant") : null, incident.personal_data ? t("personalData") : null].filter(Boolean).join(" · ");
  function addNote(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    update.mutate({ kind: "note", note: String(new FormData(form).get("note") ?? "") }, { onSuccess: () => form.reset() });
  }
  function classify(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const at = String(new FormData(e.currentTarget).get("classified_at") ?? "");
    update.mutate({ kind: "classified", classified_at: new Date(at).toISOString(), note: "" });
  }
  return <div className="panel-grid">
    <PageHeader crumbs={[...crumbs, { label: incident.title }]} title={incident.title}
      description={<>{t("aware")}: {time(incident.aware_at)} · {flags || t("noFlags")}
        {incident.classified_at ? <> · {t("classified", { time: time(incident.classified_at) })}</> : incident.significant ? <> · {t("classificationMissing")}</> : null}</>}
      actions={canAct
        // Sending a notice is the primary action; closing is secondary and asks first while
        // a notice is still unsent (console-unification spec).
        ? confirming ? <span className="confirm-row" role="group" aria-label={t("close")}>
            <span>{t("closeConfirm", { count: unsent })}</span>
            <button type="button" className="button-danger" disabled={update.isPending} onClick={close}>{t("closeAnyway")}</button>
            <button type="button" className="dashboard-button" onClick={() => setConfirming(false)}>{t("cancel")}</button>
          </span>
          : <button type="button" className="dashboard-button" disabled={update.isPending} onClick={() => (unsent > 0 ? setConfirming(true) : close())}>{t("close")}</button>
        : incident.closed_at ? <Badge state="incidentClosed">{t("closed")}</Badge> : null} />
    {update.isError ? <ErrorMessage error={update.error} /> : null}
    {update.isSuccess && !open ? <p role="status" className="notice"><Icon name="done" />{t("closedEvidence")}</p> : null}
    <Panel title={t("clocks")} description={t("clocksHelp")}>
      {open && incident.significant && incident.classified_at === null
        ? <p className="notice" data-severity="overdue" role="note"><Icon name="overdue" />{t("classificationMissingNotice")}</p> : null}
      {canAct && incident.classified_at === null ? <section className="classify-block" aria-labelledby={`${classifyId}-title`}>
        <h3 id={`${classifyId}-title`}>{t("classifyTitle")}</h3>
        <p id={`${classifyId}-help`} className="text-sm text-muted">{t("classifiedHelp")}</p>
        <form onSubmit={classify} className="routine-form">
          <span><label htmlFor={classifyId}>{t("classifiedAt")}</label><input id={classifyId} name="classified_at" type="datetime-local" required
            min={localInput(new Date(incident.aware_at))} max={localInput(new Date())} aria-describedby={`${classifyId}-help`} /></span>
          <div className="form-actions"><button type="submit" className="dashboard-button" disabled={update.isPending}>{t("classify")}</button></div>
        </form>
      </section> : null}
      {incident.clocks.length === 0 ? <p className="text-muted">{t("noClocks")}</p>
        : <div className="table-region" role="region" aria-label={t("clocks")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("clock")}</th><th scope="col">{t("due")}</th><th scope="col">{t("status")}</th></tr></thead>
          <tbody>{incident.clocks.map((c) => <tr key={c.ref}>
            <td data-label={t("clock")}>{title(c)}<span className="block text-sm text-muted">{c.framework_name} · {c.requirement}</span></td>
            <td data-label={t("due")} className="tabular-nums">{c.due_at ? time(c.due_at) : "—"}</td>
            <td data-label={t("status")}><ClockStatus clock={c} time={time} />
              {canAct && (c.state === "running" || c.state === "overdue")
                ? <button type="button" className="button-primary clock-action" disabled={update.isPending}
                  onClick={() => update.mutate({ kind: "clock", clock: c.ref, note: "" })}>{t("sent")}<span className="sr-only">{t("sentWhich", { clock: title(c) })}</span></button> : null}</td>
          </tr>)}</tbody>
        </table></div>}
    </Panel>
    <Panel title={t("updates")}>
      {incident.updates.length === 0 ? <p className="text-muted">{t("noUpdates")}</p>
        : <ol className="update-list">{incident.updates.map((u) => <li key={`${u.recorded_at}:${u.kind}:${u.clock ?? ""}`}>
          <span className="text-sm text-muted tabular-nums">{time(u.recorded_at)}</span>
          <span>{u.kind === "clock" ? t("kind.clock", { clock: u.clock && byRef.has(u.clock) ? title(byRef.get(u.clock)!) : u.clock ?? "" })
            : u.kind === "classified" ? t("kind.classified", { time: u.classified_at ? time(u.classified_at) : "" }) : t(`kind.${u.kind}`)}
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
      ? <Badge state="clockMetLate">{t("metLate", { time: time(clock.met_at) })}</Badge>
      : <Badge state="clockMet">{t("met", { time: time(clock.met_at) })}</Badge>;
  }
  if ((clock.state === "overdue" || clock.state === "running") && clock.due_at) return <ClockBadge dueAt={clock.due_at} />;
  if (clock.state === "overdue") return <Badge state="clockOverdue">{t("late")}</Badge>;
  if (clock.state === "running") return <Badge state="clockRunning">{t("running")}</Badge>;
  return <span className="text-sm text-muted">{t("waiting")}</span>;
}
