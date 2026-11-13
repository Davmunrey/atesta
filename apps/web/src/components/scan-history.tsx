"use client";

import { useFormatter, useTranslations } from "next-intl";
import type { components } from "@/lib/api/schema";

export function ScanHistory({ scans, evidenceCount }: { scans: components["schemas"]["ScanSummary"][]; evidenceCount: number }) {
  const t = useTranslations("dashboard");
  const format = useFormatter();
  return <aside className="collection-summary" aria-label={t("collectionSummary")}>
    <section aria-labelledby="scans-heading">
      <h2 id="scans-heading">{t("scans")}</h2>
      {scans.length === 0 ? <div className="dashboard-empty"><h3>{t("emptyScans")}</h3><p>{t("emptyScansHelp")}</p></div> : <ol className="scan-history">
        {scans.map((scan) => <li key={scan.id}>
          <div className="scan-heading"><strong>{t(`providers.${scan.provider}`)}</strong><span className="scan-status" data-status={scan.status}>{t(`statuses.${scan.status}`)}</span></div>
          <time dateTime={scan.queued_at}>{format.dateTime(new Date(scan.queued_at), { dateStyle: "medium", timeStyle: "short" })}</time>
          <p>{scan.expected_checks > 0 ? t("coverage", { evaluated: scan.evaluated_checks, expected: scan.expected_checks }) : t("unknownCoverage")}</p>
          {scan.expected_checks > 0 ? <progress max={scan.expected_checks} value={scan.evaluated_checks} aria-label={t("coverageLabel", { provider: t(`providers.${scan.provider}`) })} /> : null}
        </li>)}
      </ol>}
    </section>
    <section className="evidence-summary" aria-labelledby="evidence-heading">
      <h2 id="evidence-heading">{t("evidence")}</h2>
      <p className="evidence-count">{format.number(evidenceCount)} <span>{t("evidenceUnit", { count: evidenceCount })}</span></p>
      <p className="text-sm text-muted">{evidenceCount ? t("evidenceHelp") : t("emptyEvidenceHelp")}</p>
    </section>
  </aside>;
}
