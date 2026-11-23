"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { type Report, useReport } from "@/lib/api/report";
import { type Membership, orgHome } from "@/lib/org";
import { ErrorMessage } from "./error-message";
import { PageHeader } from "./page-frame";

const DONE = ["measures_assessed", "assessments_reviewed", "evidence_by_people", "evidence_by_tools", "policies_approved",
  "access_reviews_closed", "trainings_closed", "incidents_recorded", "incidents_closed", "deadlines_met", "people_joined"] as const;

/** The monthly report for management (management-report spec): printable, counts only. */
export function ReportView({ org, initialMonth }: { org: Membership; initialMonth: string }) {
  const t = useTranslations("report");
  const [month, setMonth] = useState(initialMonth);
  const monthId = useId();
  const query = useReport(org.organization_id, month);
  const crumbs = [{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }];
  return <div className="dossier">
    <div className="dossier-toolbar">
      <PageHeader crumbs={crumbs} title={t("title")} description={t("intro")}
        actions={<button type="button" className="button-primary" onClick={() => window.print()} disabled={!query.data}>{t("print")}</button>} />
      <p className="routine-form"><span><label htmlFor={monthId}>{t("month")}</label>
        <input id={monthId} type="month" value={month} max={initialMonth} onChange={(e) => e.target.value && setMonth(e.target.value)} /></span></p>
    </div>
    {query.isPending ? <p role="status">{t("loading")}</p> : query.isError ? <ErrorMessage error={query.error} /> : <Body report={query.data} orgName={org.organization_name} />}
  </div>;
}

function Body({ report, orgName }: { report: Report; orgName: string }) {
  const t = useTranslations("report");
  const d = useTranslations("dossier");
  const due = useTranslations("cockpit.attention.due");
  const format = useFormatter();
  const english = useLocale() === "en";
  const monthName = format.dateTime(new Date(`${report.month}-01T12:00:00Z`), { month: "long", year: "numeric", timeZone: "UTC" });
  const total = DONE.reduce((n, k) => n + report.done[k], 0);
  return <>
    <section className="dossier-section" aria-labelledby="report-cover">
      <p className="text-sm text-muted">{t("kicker")}</p>
      <h2 id="report-cover" className="page-title">{orgName} · {monthName}</h2>
      <p className="notice">{t("notCertification")}</p>
      <div className="dossier-signature" aria-label={d("signature")}>
        {(["name", "role", "date", "sign"] as const).map((k) => <p key={k}><span>{d(`signer.${k}`)}</span><span className="dossier-line" /></p>)}
      </div>
    </section>
    <section className="dossier-section" aria-labelledby="report-done">
      <h2 id="report-done">{t("done", { month: monthName })}</h2>
      {total === 0 ? <p className="text-muted">{t("nothingDone")}</p>
        : <dl className="dossier-counts">{DONE.filter((k) => report.done[k] > 0).map((k) =>
          <div key={k}><dt>{t(`lines.${k}`)}</dt><dd className="tabular-nums">{format.number(report.done[k])}</dd></div>)}</dl>}
    </section>
    <section className="dossier-section" aria-labelledby="report-status">
      <h2 id="report-status">{t("status")}</h2>
      <p className="text-sm text-muted">{t("statusHelp")}</p>
      {report.frameworks.length === 0 ? <p className="text-muted">{t("noFrameworks")}</p>
        : <div className="table-region" role="region" aria-label={t("status")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("framework")}</th><th scope="col">{t("assessed")}</th><th scope="col">{t("implemented")}</th><th scope="col">{t("overdue")}</th><th scope="col">{t("review")}</th></tr></thead>
          <tbody>{report.frameworks.map((f) => <tr key={f.key}>
            <td data-label={t("framework")}>{f.name}</td><td data-label={t("assessed")} className="tabular-nums">{t("ofTotal", { done: f.assessed, total: f.total })}</td>
            <td data-label={t("implemented")} className="tabular-nums">{format.number(f.implemented)}</td><td data-label={t("overdue")} className="tabular-nums">{format.number(f.overdue)}</td>
            <td data-label={t("review")}>{f.review_on ? format.dateTime(new Date(`${f.review_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) : t("noReview")}</td>
          </tr>)}</tbody>
        </table></div>}
    </section>
    <section className="dossier-section" aria-labelledby="report-due">
      <h2 id="report-due">{t("due")}</h2>
      {report.due.length === 0 ? <p className="text-muted">{t("nothingDue")}</p>
        : <ul className="dossier-list">{report.due.map((i) => {
          const date = i.due_on ? format.dateTime(new Date(`${i.due_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) : "";
          const text = i.kind === "incident_clock" && i.clock && i.due_at
            ? due("incident_clock", { clock: english ? i.clock.en : i.clock.es, framework: i.clock.framework, title: i.title,
              when: due(i.overdue ? "clockOverdue" : "clockRunning", { time: format.dateTime(new Date(i.due_at), { dateStyle: "medium", timeStyle: "short" }) }) })
            : due(i.kind as "policy_review", { title: i.title, date });
          return <li key={`${i.kind}:${i.id}:${i.clock?.en ?? ""}`} data-severity={i.overdue ? "overdue" : undefined}>{text}</li>;
        })}</ul>}
    </section>
  </>;
}
