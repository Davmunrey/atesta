"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";
import type { components } from "@/lib/api/schema";
import Link from "next/link";
import { orgFramework } from "@/lib/org";

type Framework = components["schemas"]["FrameworkSummary"];
const states = ["passed", "failed", "manual", "not_applicable"] as const;

export function FrameworkLedger({ frameworks, orgId }: { frameworks: Framework[]; orgId: string }) {
  const t = useTranslations("dashboard");
  const format = useFormatter();
  const searchId = useId();
  const [search, setSearch] = useState("");
  const query = search.trim().toLocaleLowerCase();
  // Assessed frameworks first, then those with requirements, then empty preparation templates;
  // the backend's order (by name) breaks ties.
  const rank = (f: Framework) => (f.snapshot ? 0 : f.requirements > 0 ? 1 : 2);
  const visible = frameworks.filter((f) => `${f.name} ${f.key}`.toLocaleLowerCase().includes(query))
    .map((f, i) => [f, i] as const).sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j).map(([f]) => f);
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
        <label htmlFor={searchId} className="dashboard-search-label">{t("search")}</label>
        <input id={searchId} type="search" value={search} onChange={(e) => setSearch(e.target.value)} className="dashboard-search" />
        <p className="sr-only" role="status">{t("matches", { count: visible.length })}</p>
        <div className="framework-ledger">
          {visible.map((framework, index) => {
            const snapshot = framework.snapshot;
            const total = snapshot ? states.reduce((sum, state) => sum + snapshot[state], 0) : 0;
            return <details key={framework.key} className="framework-row" open={index === 0 && snapshot !== null}>
              <summary>
                <span className="framework-name"><strong>{framework.name}</strong>
                  <span>{framework.requirements > 0 ? t("requirementCount", { count: framework.requirements }) : t("preparationOnly")}{framework.status === "draft" ? ` · ${t("draft")}` : ""}</span>
                  {snapshot && snapshot.manual > 0 ? <span>{t("pendingReviews", { count: snapshot.manual })}</span> : null}
                </span>
                <span className="framework-score">{snapshot === null ? t("notAssessed") : snapshot.score === null ? t("unscored") : `${format.number(snapshot.score, { maximumFractionDigits: 1 })} %`}</span>
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
                <Link href={orgFramework(orgId, framework.key)} className="framework-detail-link">{t("viewRequirements")}</Link>
              </div>
            </details>;
          })}
        </div>
        {visible.length === 0 ? <div className="dashboard-empty"><p>{t("noMatches")}</p><button className="dashboard-button" onClick={() => setSearch("")}>{t("clearSearch")}</button></div> : null}
      </>}
    </section>
  );
}
