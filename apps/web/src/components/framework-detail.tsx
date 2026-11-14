"use client";

import Link from "next/link";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useFrameworkDetail } from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { orgHome } from "@/lib/org";
import { type Role, canReviewControls } from "@/lib/permissions";
import { CatalogPreparation, PreparationGuides, RequirementGuidance } from "./catalog-preparation";
import { CatalogReference as Reference } from "./catalog-reference";
import { ControlReview } from "./control-review";
import { ErrorMessage } from "./error-message";

type Detail = components["schemas"]["FrameworkDetail"];
type Requirement = components["schemas"]["RequirementDetail"];
const statuses = ["fail", "manual", "not_evaluated", "pass", "not_applicable"] as const;
type Filter = "all" | typeof statuses[number];

/** role is a UI hint only: it hides the review form from members. The API decides. */
export function FrameworkDetailView({ orgId, frameworkKey, role = "member" }: { orgId: string; frameworkKey: string; role?: Role }) {
  const t = useTranslations("framework");
  const dashboard = useTranslations("dashboard");
  const format = useFormatter();
  const query = useFrameworkDetail(orgId, frameworkKey);
  return <section className="framework-page">
    <Link href={orgHome(orgId)} className="framework-back">{t("back")}</Link>
    {query.isPending ? <div className="dashboard-loading" role="status" aria-busy="true"><p>{t("loading")}</p><div className="dashboard-skeleton" aria-hidden="true" /></div>
      : query.isError ? <div className="dashboard-error"><ErrorMessage error={query.error} /><button className="dashboard-button" onClick={() => void query.refetch()}>{dashboard("retry")}</button></div>
      : <>
        <div className="framework-title"><div><h1 className="page-title">{query.data.name}</h1><p className="text-muted">{t("intro")}</p></div>
          <button className="dashboard-button" disabled={query.isFetching} onClick={() => void query.refetch()}>{dashboard(query.isFetching ? "refreshing" : "refresh")}</button>
        </div>
        {query.data.development ? <p className="framework-environment">{t("development")}</p> : null}
        {query.data.snapshot ? <div className="framework-record">
          <p><strong>{t("recordedScore")}</strong> {query.data.snapshot.score === null ? dashboard("unscored") : `${format.number(query.data.snapshot.score, { maximumFractionDigits: 1 })} %`}</p>
          <p><time dateTime={query.data.snapshot.computed_at}>{format.dateTime(new Date(query.data.snapshot.computed_at), { dateStyle: "medium", timeStyle: "short" })}</time> · {dashboard("version", { version: query.data.snapshot.framework_version })} · {dashboard("organizationScope")}</p>
        </div> : <p className="framework-notice">{t("unassessed")}</p>}
        {query.data.snapshot && !query.data.catalog_matches_snapshot ? <p className="framework-notice">{t("catalogChanged")}</p> : null}
        {query.data.catalog_context ? <CatalogPreparation context={query.data.catalog_context} requirements={query.data.requirements.length} controls={query.data.preparation_controls?.length ?? 0} /> : null}
        <RequirementRegister key={`${orgId}:${frameworkKey}`} detail={query.data} review={{ orgId, frameworkKey, canReview: canReviewControls(role) }} />
        <PreparationGuides controls={query.data.preparation_controls ?? []} />
        <div className="framework-catalog"><h2>{t("catalogTitle")}</h2><p>{t("currentVersion", { version: query.data.version, catalog: query.data.catalog_version ?? t("unknownVersion") })}</p>
          <p>{t("catalogHelp")}</p><Reference value={query.data.source} />
        </div>
        <p className="dashboard-note">{dashboard("assessmentNote")}</p>
      </>}
  </section>;
}

type ReviewContext = { orgId: string; frameworkKey: string; canReview: boolean };

function RequirementRegister({ detail, review }: { detail: Detail; review: ReviewContext }) {
  const t = useTranslations("framework");
  const locale = useLocale();
  const searchId = useId();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const needle = search.trim().toLocaleLowerCase(locale);
  const visible = detail.requirements.filter((r) => (filter === "all" || r.status === filter)
    && [r.code, r.title_es, r.title_en, ...r.controls.flatMap((c) => [c.key, c.title_es, c.title_en, ...c.checks.map((check) => check.check_id)])].join(" ").toLocaleLowerCase(locale).includes(needle))
    .sort((a, b) => statuses.indexOf(a.status) - statuses.indexOf(b.status) || (a.guidance?.section ?? a.code).localeCompare(b.guidance?.section ?? b.code, locale, { numeric: true }));
  return <section aria-labelledby="requirements-heading" className="requirement-register">
    <h2 id="requirements-heading">{t("requirements")}</h2><p className="text-muted">{t("registerHelp")}</p>
    {detail.requirements.length === 0 ? <div className="dashboard-empty"><h3>{t("empty")}</h3><p>{t("emptyHelp")}</p></div> : <>
      <div role="group" aria-label={t("filter")} className="requirement-filters">
        {(["all", ...statuses] as const).map((state) => <button key={state} aria-pressed={filter === state} onClick={() => setFilter(state)} className="dashboard-button">
          {t(`states.${state}`)} <span>{state === "all" ? detail.requirements.length : detail.requirements.filter((r) => r.status === state).length}</span>
        </button>)}
      </div>
      <label htmlFor={searchId} className="dashboard-search-label">{t("search")}</label>
      <input id={searchId} type="search" className="dashboard-search" value={search} onChange={(e) => setSearch(e.target.value)} />
      <p className="requirement-match" role="status">{t("matches", { shown: visible.length, total: detail.requirements.length })}</p>
      <div className="requirement-list">{visible.map((requirement, index) => <RequirementRow key={requirement.code} requirement={requirement} initiallyOpen={index === 0} review={review} />)}</div>
      {visible.length === 0 ? <div className="dashboard-empty"><p>{t("noMatches")}</p><button className="dashboard-button" onClick={() => { setFilter("all"); setSearch(""); }}>{t("clear")}</button></div> : null}
    </>}
  </section>;
}

function RequirementRow({ requirement: r, initiallyOpen, review }: { requirement: Requirement; initiallyOpen: boolean; review: ReviewContext }) {
  const t = useTranslations("framework");
  const english = useLocale() === "en";
  const title = (english ? r.title_en ?? r.title_es : r.title_es) ?? t("historicalTitle");
  return <details className="requirement-row" open={initiallyOpen}>
    <summary><span className="requirement-heading"><span className="requirement-code">{r.code}</span><strong>{title}</strong></span>
      <span className="requirement-state" data-state={r.status}>{t(`states.${r.status}`)}</span>
      <svg className="disclosure-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg>
    </summary>
    <div className="requirement-body">
      <p className="requirement-explanation">{t(`meaning.${r.status}`)}</p>
      <h3>{t("nextStep")}</h3><p>{t(`next.${r.status}`)}</p>
      {!r.in_current_catalog ? <p className="framework-notice">{t("historicalHelp")}</p> : null}
      {r.applies_to.length > 0 ? <p className="text-sm text-muted">{t("applicability")}: {r.applies_to.join(", ")}</p> : null}
      {r.guidance ? <RequirementGuidance guidance={r.guidance} /> : null}
      {r.source ? <p className="requirement-source">{t("source")}: <Reference value={r.source} /></p> : null}
      <div className="control-guides"><h3>{t("configurations")}</h3>
        {r.controls.length === 0 ? <p className="text-muted">{t("noControls")}</p> : r.controls.map((control) => <article className="control-guide" key={control.key}>
          <div className="control-heading"><h4>{english ? control.title_en : control.title_es}</h4><span className="requirement-state" data-state={control.observed_status ?? "not_evaluated"}>{control.manual ? t("manualControl") : t(`observations.${control.observed_status ?? "missing"}`)}</span></div>
          <p className="requirement-code">{control.key}</p>
          <p className="control-description">{(english ? control.description_en : control.description_es).trim() || t("missingGuide")}</p>
          <p className="text-sm text-muted">{control.manual ? t("manualHelp") : t("observationHelp")}</p>
          {!control.mapping_reviewed ? <p className="text-sm text-muted">{t("mappingUnreviewed")}</p> : null}
          {control.checks.length > 0 ? <ul className="configuration-checks" aria-label={t("checks")}>{control.checks.map((check) => <li key={`${check.engine}:${check.check_id}`}>
            <span><span className="requirement-code">{check.check_id}</span><span className="check-engine">{check.engine}</span></span><span>{t(`observations.${check.observed_status ?? "missing"}`)}</span>
          </li>)}</ul> : null}
          {control.manual ? <ControlReview {...review} controlKey={control.key} review={control.review ?? null} /> : null}
          <div className="control-references"><h5>{t("applyGuide")}</h5>{control.remediation_refs.length ? <ul>{control.remediation_refs.map((value, i) => <li key={i}><Reference value={value} /></li>)}</ul> : <p>{t("missingReferences")}</p>}</div>
        </article>)}
      </div>
    </div>
  </details>;
}
