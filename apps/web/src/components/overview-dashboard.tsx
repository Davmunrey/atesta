"use client";

import { useTranslations } from "next-intl";
import { useOverview } from "@/lib/api/hooks";
import { useReadiness } from "@/lib/api/register-hooks";
import type { Membership } from "@/lib/org";
import { ErrorMessage } from "./error-message";
import { FirstSteps } from "./first-steps";
import { FrameworkLedger } from "./framework-ledger";
import { GettingStarted } from "./getting-started";
import { PageHeader } from "./page-frame";
import { AttentionList, Kpis, ReadinessSummary, RecentActivity, TeamLoad, YourWork, started, useAttention } from "./readiness";
import { ScanHistory } from "./scan-history";

/** The organization's overview as a console (readiness-cockpit and console-shell specs). */
export function OverviewDashboard({ orgId, org }: { orgId: string; org?: Membership }) {
  const t = useTranslations("dashboard");
  const query = useOverview(orgId);
  const readinessQuery = useReadiness(orgId);
  const membership: Membership = org ?? { organization_id: orgId, organization_name: "", role: "member", access_expires_on: null, closure_erase_after: null };
  const readiness = readinessQuery.data ?? [];
  const attention = useAttention(membership, readiness);
  const header = (description?: React.ReactNode, actions?: React.ReactNode) => org
    ? <PageHeader title={org.organization_name} description={description} actions={actions} /> : null;
  if (query.isPending) return <>{header()}<div className="dashboard-loading" role="status" aria-busy="true">
    <p>{t("loading")}</p><div className="dashboard-skeleton" aria-hidden="true" /><div className="dashboard-skeleton" aria-hidden="true" />
  </div></>;
  if (query.isError) return <>{header()}<div className="dashboard-error"><ErrorMessage error={query.error} /><button className="dashboard-button" onClick={() => void query.refetch()}>{t("retry")}</button></div></>;
  const underway = readiness.some(started);
  const collections = query.data.scans.length > 0 || query.data.evidence_count > 0;
  const refresh = query.data.frameworks.some((f) => f.snapshot) || query.data.scans.length > 0
    ? <button className="dashboard-button" disabled={query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? t("refreshing") : t("refresh")}</button> : null;
  const ledger = <FrameworkLedger key={orgId} frameworks={query.data.frameworks} orgId={orgId} readiness={readiness} />;
  return <div className="dashboard panel-grid">
    {header(<ReadinessSummary readiness={readiness} attention={attention.length} />, refresh)}
    {!org && refresh ? <div className="dashboard-toolbar">{refresh}</div> : null}
    <p className="dashboard-environment">{query.data.development ? t("development") : t("recordedResults")}</p>
    {org ? <GettingStarted org={org} readiness={readiness} /> : null}
    {underway ? <>
      <Kpis readiness={readiness} />
      <div className="panel-grid panel-grid-main">
        <AttentionList items={attention} readiness={readiness} orgId={orgId} />
        <YourWork org={membership} />
      </div>
      {ledger}
      <div className="panel-grid panel-grid-halves">
        <TeamLoad org={membership} readiness={readiness} />
        <RecentActivity org={membership} />
      </div>
    </> : <>
      <FirstSteps orgId={orgId} frameworks={query.data.frameworks} />
      {ledger}
    </>}
    {collections ? <ScanHistory scans={query.data.scans} evidenceCount={query.data.evidence_count} /> : null}
  </div>;
}
