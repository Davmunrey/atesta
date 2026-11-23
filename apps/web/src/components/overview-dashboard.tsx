"use client";

import { useTranslations } from "next-intl";
import { useOverview } from "@/lib/api/hooks";
import { useReadiness } from "@/lib/api/register-hooks";
import type { Membership } from "@/lib/org";
import { ErrorMessage } from "./error-message";
import { FirstSteps } from "./first-steps";
import { FrameworkLedger } from "./framework-ledger";
import { AttentionList, ReadinessSummary, RecentActivity, TeamLoad, YourWork, started, useAttention } from "./readiness";
import { ScanHistory } from "./scan-history";

/** The organization's cockpit (readiness-cockpit spec): how we are doing, what needs attention, who does what. */
export function OverviewDashboard({ orgId, org }: { orgId: string; org?: Membership }) {
  const t = useTranslations("dashboard");
  const query = useOverview(orgId);
  const readinessQuery = useReadiness(orgId);
  const membership: Membership = org ?? { organization_id: orgId, organization_name: "", role: "member", access_expires_on: null, closure_erase_after: null };
  const readiness = readinessQuery.data ?? [];
  const attention = useAttention(membership, readiness);
  if (query.isPending) return <div className="dashboard-loading" role="status" aria-busy="true">
    <p>{t("loading")}</p><div className="dashboard-skeleton" aria-hidden="true" /><div className="dashboard-skeleton" aria-hidden="true" />
  </div>;
  if (query.isError) return <div className="dashboard-error"><ErrorMessage error={query.error} /><button className="dashboard-button" onClick={() => void query.refetch()}>{t("retry")}</button></div>;
  const underway = readiness.some(started);
  const collections = query.data.scans.length > 0 || query.data.evidence_count > 0;
  return <div className="dashboard">
    <ReadinessSummary readiness={readiness} attention={attention.length} />
    <div className="dashboard-toolbar">
      <p>{query.data.development ? t("development") : t("recordedResults")}</p>
      {query.data.frameworks.some((f) => f.snapshot) || query.data.scans.length > 0
        ? <button className="dashboard-button" disabled={query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? t("refreshing") : t("refresh")}</button> : null}
    </div>
    {underway ? null : <FirstSteps orgId={orgId} frameworks={query.data.frameworks} />}
    <div className={underway || collections ? "dashboard-grid" : undefined}>
      <div className="cockpit-main">
        {underway ? <AttentionList items={attention} readiness={readiness} orgId={orgId} /> : null}
        <FrameworkLedger key={orgId} frameworks={query.data.frameworks} orgId={orgId} readiness={readiness} />
      </div>
      {underway || collections ? <aside className="cockpit-side" aria-label={t("supporting")}>
        {underway ? <><YourWork org={membership} /><TeamLoad org={membership} readiness={readiness} /><RecentActivity org={membership} /></> : null}
        {collections ? <ScanHistory scans={query.data.scans} evidenceCount={query.data.evidence_count} /> : null}
      </aside> : null}
    </div>
  </div>;
}
