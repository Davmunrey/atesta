"use client";

import Link from "next/link";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useFrameworkDetail } from "@/lib/api/hooks";
import { groupByPrefix, useRegister, type Register } from "@/lib/api/register-hooks";
import type { components } from "@/lib/api/schema";
import { orgHome } from "@/lib/org";
import { type Role, canReviewControls } from "@/lib/permissions";
import { CatalogPreparation, PreparationGuides, RequirementGuidance } from "./catalog-preparation";
import { CatalogReference as Reference } from "./catalog-reference";
import { ControlReview } from "./control-review";
import { ControlEvidence } from "./control-evidence";
import { ErrorMessage } from "./error-message";
import { AssessmentBadge, AssessmentForm, SelfAssessmentPanel } from "./self-assessment";

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
  const registerQuery = useRegister(orgId, frameworkKey);
  // A framework with no register (404) or no requirements keeps the recorded-results view only.
  const register = registerQuery.data && registerQuery.data.items.length > 0 ? registerQuery.data : null;
  const canEdit = canReviewControls(role);
  return <section className="framework-page">
    <Link href={orgHome(orgId)} className="framework-back">{t("back")}</Link>
    {query.isPending ? <div className="dashboard-loading" role="status" aria-busy="true"><p>{t("loading")}</p><div className="dashboard-skeleton" aria-hidden="true" /></div>
      : query.isError ? <div className="dashboard-error"><ErrorMessage error={query.error} /><button className="dashboard-button" onClick={() => void query.refetch()}>{dashboard("retry")}</button></div>
      : <>
        <div className="framework-title"><div><h1 className="page-title">{query.data.name}</h1><p className="text-muted">{t("intro")}</p></div>
          {query.data.snapshot ? <button className="dashboard-button" disabled={query.isFetching} onClick={() => void query.refetch()}>{dashboard(query.isFetching ? "refreshing" : "refresh")}</button> : null}
        </div>
        {query.data.development ? <p className="framework-environment">{t("development")}</p> : null}
        {query.data.snapshot ? <div className="framework-record">
          <p><strong>{t("recordedScore")}</strong> {query.data.snapshot.score === null ? dashboard("unscored") : `${format.number(query.data.snapshot.score, { maximumFractionDigits: 1 })} %`}</p>
          <p><time dateTime={query.data.snapshot.computed_at}>{format.dateTime(new Date(query.data.snapshot.computed_at), { dateStyle: "medium", timeStyle: "short" })}</time> · {dashboard("version", { version: query.data.snapshot.framework_version })} · {dashboard("organizationScope")}</p>
        </div> : register ? null : <p className="framework-notice">{t("unassessed")}</p>}
        {query.data.snapshot && !query.data.catalog_matches_snapshot ? <p className="framework-notice">{t("catalogChanged")}</p> : null}
        {register ? <SelfAssessmentPanel register={register} orgId={orgId} frameworkKey={frameworkKey} canEdit={canEdit} /> : null}
        {query.data.catalog_context ? register
          ? <details className="catalog-about"><summary>{t("aboutContent")}</summary>
            <CatalogPreparation context={query.data.catalog_context} requirements={query.data.requirements.length} controls={query.data.preparation_controls?.length ?? 0} /></details>
          : <CatalogPreparation context={query.data.catalog_context} requirements={query.data.requirements.length} controls={query.data.preparation_controls?.length ?? 0} /> : null}
        <RequirementRegister key={`${orgId}:${frameworkKey}`} detail={query.data} register={register} review={{ orgId, frameworkKey, canReview: canEdit }} />
        <PreparationGuides orgId={orgId} controls={query.data.preparation_controls ?? []} />
        <div className="framework-catalog"><h2>{t("catalogTitle")}</h2>
          <p>{t("catalogHelp")}</p><Reference value={query.data.source} />
          <details className="technical-details"><summary>{t("technicalDetails")}</summary>
            <p>{t("currentVersion", { version: query.data.version, catalog: query.data.catalog_version ?? t("unknownVersion") })}</p></details>
        </div>
      </>}
  </section>;
}

type ReviewContext = { orgId: string; frameworkKey: string; canReview: boolean };
const assessmentFilters = ["all", "pending", "applies", "implemented", "not_applicable"] as const;
type AssessmentFilter = typeof assessmentFilters[number];
type Item = Register["items"][number];

function matchesAssessment(item: Item | undefined, filter: AssessmentFilter): boolean {
  const a = item?.assessment;
  if (filter === "all") return true;
  if (filter === "pending") return !a;
  if (filter === "not_applicable") return a?.applicability === "not_applicable";
  if (filter === "applies") return a?.applicability === "applies";
  return a?.applicability === "applies" && a.implementation === "implemented";
}

function RequirementRegister({ detail, register, review }: { detail: Detail; register: Register | null; review: ReviewContext }) {
  const t = useTranslations("framework");
  const r9 = useTranslations("register");
  const locale = useLocale();
  const searchId = useId();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [assessment, setAssessment] = useState<AssessmentFilter>("all");
  const items = new Map((register?.items ?? []).map((item) => [item.code, item]));
  const titles = new Map((register?.groups_es ?? []).map((g) => [g.prefix, g.title]));
  const needle = search.trim().toLocaleLowerCase(locale);
  const visible = detail.requirements.filter((r) => (filter === "all" || r.status === filter)
    && (!register || matchesAssessment(items.get(r.code), assessment))
    && [r.code, r.title_es, r.title_en, ...r.controls.flatMap((c) => [c.key, c.title_es, c.title_en, ...c.checks.map((check) => check.check_id)])].join(" ").toLocaleLowerCase(locale).includes(needle))
    .sort((a, b) => statuses.indexOf(a.status) - statuses.indexOf(b.status) || (a.guidance?.section ?? a.code).localeCompare(b.guidance?.section ?? b.code, locale, { numeric: true }));
  return <section aria-labelledby="requirements-heading" className="requirement-register">
    <h2 id="requirements-heading">{t("requirements")}</h2><p className="text-muted">{t("registerHelp")}</p>
    {detail.requirements.length === 0 ? <div className="dashboard-empty"><h3>{t("empty")}</h3><p>{t("emptyHelp")}</p></div> : <>
      {register ? <div role="group" aria-label={r9("filter")} className="requirement-filters">
        {assessmentFilters.map((state) => <button key={state} aria-pressed={assessment === state} onClick={() => setAssessment(state)} className="dashboard-button">
          {r9(`filters.${state}`)} <span>{detail.requirements.filter((r) => matchesAssessment(items.get(r.code), state)).length}</span>
        </button>)}
      </div> : null}
      {!register || detail.snapshot ? <div role="group" aria-label={t("filter")} className="requirement-filters">
        {(["all", ...statuses] as const).map((state) => <button key={state} aria-pressed={filter === state} onClick={() => setFilter(state)} className="dashboard-button">
          {t(`states.${state}`)} <span>{state === "all" ? detail.requirements.length : detail.requirements.filter((r) => r.status === state).length}</span>
        </button>)}
      </div> : null}
      <label htmlFor={searchId} className="dashboard-search-label">{t("search")}</label>
      <input id={searchId} type="search" className="dashboard-search" value={search} onChange={(e) => setSearch(e.target.value)} />
      <p className="requirement-match" role="status">{t("matches", { shown: visible.length, total: detail.requirements.length })}</p>
      {register ? <div className="requirement-list">{orderGroups(groupByPrefix([...visible].sort((a, b) => a.code.localeCompare(b.code, locale, { numeric: true }))), register.groups_es.map((g) => g.prefix)).map(([prefix, group]) =>
        <section key={prefix} className="requirement-group" aria-label={titles.get(prefix) ?? prefix}>
          <h3 className="requirement-group-heading"><span>{titles.get(prefix)
            ? <><span lang="es">{titles.get(prefix)}</span> <span className="requirement-code">{prefix}</span></>
            : <span className="requirement-code">{prefix}</span>}</span>
            <span className="text-sm text-muted">{r9("groupProgress", { assessed: group.filter((r) => items.get(r.code)?.assessment).length, total: group.length })}</span></h3>
          {group.map((requirement) => <RequirementRow key={requirement.code} requirement={requirement} initiallyOpen={false} review={review} item={items.get(requirement.code)} recorded={Boolean(detail.snapshot)} />)}
        </section>)}</div>
        : <div className="requirement-list">{visible.map((requirement, index) => <RequirementRow key={requirement.code} requirement={requirement} initiallyOpen={index === 0} review={review} />)}</div>}
      {visible.length === 0 ? <div className="dashboard-empty"><p>{t("noMatches")}</p><button className="dashboard-button" onClick={() => { setFilter("all"); setSearch(""); }}>{t("clear")}</button></div> : null}
    </>}
  </section>;
}

function RequirementRow({ requirement: r, initiallyOpen, review, item, recorded = true }: { requirement: Requirement; initiallyOpen: boolean; review: ReviewContext; item?: Item; recorded?: boolean }) {
  const t = useTranslations("framework");
  const r9 = useTranslations("register");
  const english = useLocale() === "en";
  const title = (english ? r.title_en ?? r.title_es : r.title_es) ?? t("historicalTitle");
  return <details className="requirement-row" open={initiallyOpen}>
    <summary><span className="requirement-heading"><span className="requirement-code">{r.code}</span><strong>{title}</strong></span>
      {item ? <AssessmentBadge item={item} /> : null}
      {!item || recorded ? <span className="requirement-state" data-state={r.status}>{t(`states.${r.status}`)}</span> : null}
      <svg className="disclosure-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg>
    </summary>
    <div className="requirement-body">
      {item ? <AssessmentForm item={item} orgId={review.orgId} frameworkKey={review.frameworkKey} canEdit={review.canReview} /> : null}
      <Collapsible open={!item} label={r9("guideAndText")}>
      {!item || recorded ? <><p className="requirement-explanation">{t(`meaning.${r.status}`)}</p>
      <h3>{t("nextStep")}</h3><p>{t(`next.${r.status}`)}</p></> : null}
      {!r.in_current_catalog ? <p className="framework-notice">{t("historicalHelp")}</p> : null}
      {r.applies_to.length > 0 ? <p className="text-sm text-muted">{t("applicability")}: {r.applies_to.join(", ")}</p> : null}
      {r.guidance ? <RequirementGuidance guidance={r.guidance} /> : null}
      {r.source ? <p className="requirement-source">{t("source")}: <Reference value={r.source} /></p> : null}
      </Collapsible>
      <Collapsible open={!item} label={r9("configurationAndEvidence", { count: r.controls.length })}>
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
          <ControlEvidence orgId={review.orgId} controlKey={control.key} />
          {control.manual ? <ControlReview {...review} controlKey={control.key} review={control.review ?? null} /> : null}
          <div className="control-references"><h5>{t("applyGuide")}</h5>{control.remediation_refs.length ? <ul>{control.remediation_refs.map((value, i) => <li key={i}><Reference value={value} /></li>)}</ul> : <p>{t("missingReferences")}</p>}</div>
        </article>)}
      </div>
      </Collapsible>
    </div>
  </details>;
}

/** Groups in the order the pack declares its headings (the source's own order), then the rest. */
function orderGroups<T>(groups: [string, T][], declared: string[]): [string, T][] {
  const rank = (prefix: string) => { const i = declared.indexOf(prefix); return i === -1 ? declared.length : i; };
  return [...groups].sort(([a], [b]) => rank(a) - rank(b));
}

/** Inline when nothing competes for attention; a disclosure when the assessment form leads. */
function Collapsible({ open, label, children }: { open: boolean; label: string; children: React.ReactNode }) {
  return open ? <>{children}</> : <details className="row-section"><summary>{label}</summary>{children}</details>;
}
