"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useId, useState } from "react";
import type { components } from "@/lib/api/schema";
import Link from "next/link";
import { percent } from "@/lib/format";
import type { Readiness } from "@/lib/api/register-hooks";
import { orgFramework } from "@/lib/org";
import { ReadinessBar, ReadinessCounts, StepLink } from "./readiness";

type Framework = components["schemas"]["FrameworkSummary"];
const states = ["passed", "failed", "manual", "not_applicable"] as const;
/** A handful of frameworks is scanned faster than searched (workspace-ux spec). */
const SEARCH_FROM = 8;

export function FrameworkLedger({ frameworks, orgId, readiness = [] }: { frameworks: Framework[]; orgId: string; readiness?: Readiness[] }) {
  const t = useTranslations("dashboard");
  const format = useFormatter();
  const locale = useLocale();
  const searchId = useId();
  const [search, setSearch] = useState("");
  const query = search.trim().toLocaleLowerCase();
  const progress = new Map(readiness.map((r) => [r.key, r]));
  // In progress (self-assessed or scanned) first, most advanced first; then frameworks with
  // requirements; empty preparation templates fold away at the end (readiness-cockpit spec).
  const assessed = (f: Framework) => progress.get(f.key)?.assessed ?? 0;
  const rank = (f: Framework) => (f.snapshot || assessed(f) > 0 ? 0 : f.requirements > 0 ? 1 : 2);
  const matching = frameworks.filter((f) => `${f.name} ${f.key}`.toLocaleLowerCase().includes(query))
    .map((f, i) => [f, i] as const)
    .sort(([a, i], [b, j]) => rank(a) - rank(b) || assessed(b) / Math.max(b.requirements, 1) - assessed(a) / Math.max(a.requirements, 1) || i - j)
    .map(([f]) => f);
  const visible = matching.filter((f) => f.requirements > 0);
  const templates = matching.filter((f) => f.requirements === 0);
  return (
    <section aria-labelledby="framework-heading" className="framework-section">
      <div className="dashboard-section-heading">
        <h2 id="framework-heading">{t("frameworks")}</h2>
        <span className="dashboard-count">{format.number(frameworks.length)}</span>
      </div>
      <p className="text-sm text-muted">{t("frameworksHelp")}</p>
      {frameworks.length === 0 ? <div className="dashboard-empty">
        <h3>{t("emptyFrameworks")}</h3><p>{t("emptyFrameworksHelp")}</p>
      </div> : <>
        {frameworks.length > SEARCH_FROM ? <>
          <label htmlFor={searchId} className="dashboard-search-label">{t("search")}</label>
          <input id={searchId} type="search" value={search} onChange={(e) => setSearch(e.target.value)} className="dashboard-search" />
        </> : null}
        <p className="sr-only" role="status">{t("matches", { count: matching.length })}</p>
        <div className="framework-ledger">
          {visible.map((framework, index) => {
            const snapshot = framework.snapshot;
            const r = progress.get(framework.key);
            const total = snapshot ? states.reduce((sum, state) => sum + snapshot[state], 0) : 0;
            return <details key={framework.key} className="framework-row" open={index === 0 && snapshot !== null}>
              <summary>
                <span className="framework-name"><strong>{framework.name}</strong>
                  <span>{framework.requirements > 0 ? t("requirementCount", { count: framework.requirements }) : t("preparationOnly")}{framework.status === "draft" ? ` · ${t("draft")}` : ""}</span>
                  {snapshot && snapshot.manual > 0 ? <span>{t("pendingReviews", { count: snapshot.manual })}</span> : null}
                  {r && r.assessed > 0 ? <><ReadinessBar r={r} /><ReadinessCounts r={r} /></> : null}
                </span>
                <span className="framework-score">{snapshot ? (snapshot.score === null ? t("unscored") : percent(locale, snapshot.score))
                  : r && r.assessed > 0 ? `${format.number(r.assessed)} / ${format.number(r.total)}` : t("notAssessed")}</span>
                <svg className="disclosure-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg>
              </summary>
              <div className="framework-detail">
                {snapshot ? <>
                  <dl className="result-counts">
                    {states.map((state) => <div key={state} data-result={state}><dt>{t(state)}</dt><dd>{format.number(snapshot[state])}</dd></div>)}
                  </dl>
                  {total > 0 ? <svg className="result-distribution" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true">
                    {states.map((state, index) => <rect key={state} data-result={state} x={states.slice(0, index).reduce((sum, key) => sum + snapshot[key], 0) / total * 100} width={snapshot[state] / total * 100} height="4" />)}
                  </svg> : null}
                  <dl className="snapshot-provenance">
                    <div><dt>{t("scope")}</dt><dd>{t("organizationScope")}</dd></div>
                    <div><dt>{t("assessedAt")}</dt><dd><time dateTime={snapshot.computed_at}>{format.dateTime(new Date(snapshot.computed_at), { dateStyle: "medium", timeStyle: "short" })}</time></dd></div>
                    <div><dt>{t("catalog")}</dt><dd className="font-mono">{snapshot.catalog_version}</dd></div>
                  </dl>
                  <p className="text-sm text-muted">{t("scoreHelp")}</p>
                </> : <p className="text-muted">{t("notAssessedHelp")}</p>}
                <p className="text-sm text-muted">{t("version", { version: snapshot?.framework_version ?? framework.version })}</p>
                {r ? <p><StepLink r={r} orgId={orgId} /></p> : null}
                <Link href={orgFramework(orgId, framework.key)} className="framework-detail-link">{t("viewRequirements")}</Link>
              </div>
            </details>;
          })}
        </div>
        {templates.length > 0 ? <details className="templates-fold">
          <summary>{t("templates", { count: templates.length })}</summary>
          <ul>{templates.map((f) => <li key={f.key}><Link href={orgFramework(orgId, f.key)}>{f.name}</Link> <span className="text-sm text-muted">{t("preparationOnly")}</span></li>)}</ul>
        </details> : null}
        {matching.length === 0 ? <div className="dashboard-empty"><p>{t("noMatches")}</p><button className="dashboard-button" onClick={() => setSearch("")}>{t("clearSearch")}</button></div> : null}
      </>}
    </section>
  );
}
