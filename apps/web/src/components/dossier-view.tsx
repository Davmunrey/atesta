"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { type Dossier, useDossier } from "@/lib/api/dossier";
import { type Membership, orgFramework, orgFrameworks, orgHome } from "@/lib/org";
import { ExpectedEvidence } from "./expected-evidence";
import { LoadError, Loading, PageHeader } from "@atesta/ui/page-frame";

type Requirement = Dossier["requirements"][number];

/** The auditor dossier (auditor-dossier spec): one printable document per framework. */
export function DossierView({ org, frameworkKey }: { org: Membership; frameworkKey: string }) {
  const t = useTranslations("dossier");
  const query = useDossier(org.organization_id, frameworkKey);
  const crumbs = [
    { label: org.organization_name, href: orgHome(org.organization_id) },
    { label: t("frameworks"), href: orgFrameworks(org.organization_id) },
  ];
  if (query.isPending) return <><PageHeader crumbs={crumbs} title={t("title")} /><Loading label={t("loading")} /></>;
  if (query.isError) return <><PageHeader crumbs={crumbs} title={t("title")} /><LoadError error={query.error} onRetry={() => void query.refetch()} /></>;
  const d = query.data;
  return <div className="dossier">
    <div className="dossier-toolbar">
      <PageHeader crumbs={[...crumbs, { label: d.framework_name, href: orgFramework(org.organization_id, frameworkKey) }, { label: t("title") }]}
        title={t("title")} description={t("intro")}
        actions={<button type="button" className="button-primary" onClick={() => window.print()}>{t("print")}</button>} />
    </div>
    <Cover d={d} orgName={org.organization_name} />
    <Summary d={d} />
    <Applicability d={d} />
    <Evidence d={d} />
    <Routines d={d} />
  </div>;
}

function Cover({ d, orgName }: { d: Dossier; orgName: string }) {
  const t = useTranslations("dossier");
  const format = useFormatter();
  return <section className="dossier-section dossier-cover" aria-labelledby="dossier-cover">
    <p className="text-sm text-muted">{t("coverKicker")}</p>
    <h2 id="dossier-cover" className="page-title">{d.framework_name}</h2>
    <dl className="dossier-facts">
      <div><dt>{t("organization")}</dt><dd>{orgName}</dd></div>
      <div><dt>{t("version")}</dt><dd>{d.framework_version}</dd></div>
      <div><dt>{t("catalog")}</dt><dd className="font-mono break-all">{d.catalog_version ?? "—"}</dd></div>
      <div><dt>{t("generated")}</dt><dd>{format.dateTime(new Date(d.generated_at), { dateStyle: "long", timeStyle: "short" })}</dd></div>
    </dl>
    <p className="notice">{t("notCertification")}</p>
    <div className="dossier-signature" aria-label={t("signature")}>
      {(["name", "role", "date", "sign"] as const).map((k) => <p key={k}><span>{t(`signer.${k}`)}</span><span className="dossier-line" /></p>)}
    </div>
  </section>;
}

function Summary({ d }: { d: Dossier }) {
  const t = useTranslations("dossier");
  const format = useFormatter();
  const c = d.summary.counts;
  const r = d.summary.routines;
  const pending = [
    ["policiesDue", r.policies_due], ["policiesUnapproved", r.policies_unapproved], ["accessReviewsOverdue", r.access_reviews_overdue],
    ["trainingsUnclosed", r.trainings_unclosed], ["incidentClocksOverdue", r.incident_clocks_overdue],
  ] as const;
  return <section className="dossier-section" aria-labelledby="dossier-summary">
    <h2 id="dossier-summary">{t("summary")}</h2>
    <p className="text-sm text-muted">{t("summaryHelp")}</p>
    {c ? <dl className="dossier-counts">
      {([["total", c.total], ["assessed", c.assessed], ["implemented", c.implemented], ["partial", c.partial],
        ["notImplemented", c.not_implemented], ["notApplicable", c.not_applicable], ["overdue", c.overdue]] as const).map(([k, v]) =>
        <div key={k}><dt>{t(`counts.${k}`)}</dt><dd className="tabular-nums">{format.number(v)}</dd></div>)}
    </dl> : <p>{t("noRequirements")}</p>}
    <h3>{t("review")}</h3>
    {d.summary.review
      ? <p>{t("reviewBy", { name: d.summary.review.reviewer_name, role: d.summary.review.reviewer_role,
        date: format.dateTime(new Date(`${d.summary.review.reviewed_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) })}<span className="block">{d.summary.review.conclusions}</span></p>
      : <p className="text-muted">{t("noReview")}</p>}
    <h3>{t("routinesState")}</h3>
    {pending.every(([, n]) => n === 0) ? <p>{t("routinesClear")}</p>
      : <ul className="dossier-list">{pending.filter(([, n]) => n > 0).map(([k, n]) => <li key={k}>{t(`pending.${k}`, { count: n })}</li>)}</ul>}
  </section>;
}

function Applicability({ d }: { d: Dossier }) {
  const t = useTranslations("dossier");
  const s = useTranslations("register.states");
  return <section className="dossier-section" aria-labelledby="dossier-soa">
    <h2 id="dossier-soa">{t("applicability")}</h2>
    <div className="table-region" role="region" aria-label={t("applicability")} tabIndex={0}><table className="w-full text-left">
      <thead><tr><th scope="col">{t("code")}</th><th scope="col">{t("measure")}</th><th scope="col">{t("decision")}</th><th scope="col">{t("implementation")}</th><th scope="col">{t("justification")}</th></tr></thead>
      <tbody>{d.applicability.map((row) => <tr key={row.code}>
        <td data-label={t("code")} className="font-mono">{row.code}</td><td data-label={t("measure")} lang="es">{row.title_es}</td>
        <td data-label={t("decision")}>{t(`decisions.${row.decision}`)}</td>
        <td data-label={t("implementation")}>{row.decision === "not_applicable" ? s("not_applicable") : row.implementation ? s(row.implementation) : s("pending")}</td>
        <td data-label={t("justification")}>{row.justification}</td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}

function Evidence({ d }: { d: Dossier }) {
  const t = useTranslations("dossier");
  return <section className="dossier-section" aria-labelledby="dossier-evidence">
    <h2 id="dossier-evidence">{t("evidence")}</h2>
    <p className="text-sm text-muted">{t("evidenceHelp")}</p>
    {d.requirements.filter((r) => r.controls.length > 0 || r.expected_evidence).map((r) => <RequirementEvidence key={r.code} r={r} />)}
  </section>;
}

function RequirementEvidence({ r }: { r: Requirement }) {
  const t = useTranslations("dossier");
  const o = useTranslations("framework.observations");
  const format = useFormatter();
  const english = useLocale() === "en";
  const title = english && r.title_en ? r.title_en : r.title_es;
  return <article className="dossier-requirement">
    <h3><span className="font-mono">{r.code}</span> <span lang={english && r.title_en ? undefined : "es"}>{title}</span></h3>
    {r.expected_evidence ? <ExpectedEvidence evidence={r.expected_evidence} variant="print" /> : null}
    {r.controls.map((c) => <div key={c.key} className="dossier-control">
      <p><strong>{english ? c.title_en : c.title_es}</strong> · {c.manual
        ? (c.review ? t("reviewed", { date: format.dateTime(new Date(c.review.reviewed_at), { dateStyle: "medium" }) }) : t("notReviewed"))
        : o(c.observed_status ?? "missing")}</p>
      {c.manual && c.review ? <p className="text-sm">{c.review.evidence.length === 0 ? t("reviewCitesNone")
        : t("reviewCites", { count: c.review.evidence.length, titles: format.list(c.review.evidence.map((e) => e.title), { type: "conjunction" }) })}</p> : null}
      {c.evidence.length === 0 ? <p className="text-sm text-muted">{t("noEvidence")}</p>
        : <ul className="dossier-list">{c.evidence.map((e, i) => <li key={i}>
          <span className="text-sm text-muted">{format.dateTime(new Date(e.collected_at), { dateStyle: "medium" })} · {t(`sources.${e.source_type}`)}</span>
          <span className="block"><strong>{e.title}</strong>. {e.statement}</span>
          {e.reference_url ? <a href={e.reference_url} className="text-link underline text-sm" rel="noopener noreferrer" target="_blank">{e.reference_url}</a> : null}
        </li>)}</ul>}
    </div>)}
  </article>;
}

function Routines({ d }: { d: Dossier }) {
  const t = useTranslations("dossier");
  const format = useFormatter();
  const day = (v: string) => format.dateTime(new Date(v.length === 10 ? `${v}T00:00:00Z` : v), { dateStyle: "medium", ...(v.length === 10 ? { timeZone: "UTC" } : {}) });
  const { policies, access_reviews, trainings, incidents } = d.routines;
  return <section className="dossier-section" aria-labelledby="dossier-routines">
    <h2 id="dossier-routines">{t("routines")}</h2>
    <h3>{t("policies")}</h3>
    {policies.length === 0 ? <p className="text-muted">{t("none")}</p> : <ul className="dossier-list">{policies.map((p) => <li key={p.id}>
      <strong>{p.title}</strong>: {p.latest ? t("policyApproved", { version: p.latest.version, approver: p.latest.approver_name, date: day(p.latest.approved_on) }) : t("policyUnapproved")}
      {p.next_review_on ? <> · {t("nextReview", { date: day(p.next_review_on) })}</> : null}</li>)}</ul>}
    <h3>{t("accessReviews")}</h3>
    {access_reviews.length === 0 ? <p className="text-muted">{t("none")}</p> : <ul className="dossier-list">{access_reviews.map((r) => <li key={r.id}>
      <strong>{r.title}</strong> ({r.system}): {t("accessReviewClosed", { total: r.total, keep: r.keep, revoke: r.revoke, date: day(r.closed_at!) })}</li>)}</ul>}
    <h3>{t("trainings")}</h3>
    {trainings.length === 0 ? <p className="text-muted">{t("none")}</p> : <ul className="dossier-list">{trainings.map((c) => <li key={c.id}>
      <strong>{c.title}</strong>: {t("trainingClosed", { count: c.acknowledged, date: day(c.closed_at!) })}</li>)}</ul>}
    <h3>{t("incidents")}</h3>
    {incidents.length === 0 ? <p className="text-muted">{t("none")}</p> : <ul className="dossier-list">{incidents.map((i) => <li key={i.id}>
      <strong>{i.title}</strong>: {t("incidentClosed", { aware: day(i.aware_at), date: day(i.closed_at!) })}</li>)}</ul>}
  </section>;
}
