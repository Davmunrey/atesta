"use client";

import { useTranslations } from "next-intl";
import { useOverview } from "@/lib/api/hooks";
import { useReadiness } from "@/lib/api/register-hooks";
import type { Membership } from "@/lib/org";
import { FirstSteps } from "./first-steps";
import { FrameworkLines } from "./framework-lines";
import { GettingStarted } from "./getting-started";
import { LoadError, PageHeader } from "./page-frame";
import { RecordsGlance } from "./records-glance";
import { AttentionList, started, useAttention } from "./readiness";

/**
 * The organization's home is a task list (console-unification spec, owner decision 2026-11-24):
 * what needs someone now comes first, then one line per framework, then the records.
 */
export function OverviewDashboard({ orgId, org }: { orgId: string; org?: Membership }) {
  const t = useTranslations("dashboard");
  const query = useOverview(orgId);
  const readinessQuery = useReadiness(orgId);
  const membership: Membership = org ?? { organization_id: orgId, organization_name: "", role: "member", access_expires_on: null, closure_erase_after: null };
  const readiness = readinessQuery.data ?? [];
  const tasks = useAttention(membership, readiness);
  const header = (actions?: React.ReactNode) => org ? <PageHeader title={org.organization_name} actions={actions} /> : null;
  if (query.isPending) return <>{header()}<div className="dashboard-loading" role="status" aria-busy="true">
    <p>{t("loading")}</p><div className="dashboard-skeleton" aria-hidden="true" /><div className="dashboard-skeleton" aria-hidden="true" />
  </div></>;
  if (query.isError) return <>{header()}<LoadError error={query.error} onRetry={() => void query.refetch()} /></>;
  const underway = readiness.some(started);
  const refresh = query.data.frameworks.some((f) => f.snapshot) || query.data.scans.length > 0
    ? <button className="dashboard-button" disabled={query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? t("refreshing") : t("refresh")}</button> : null;
  return <div className="dashboard panel-grid">
    {header(refresh)}
    {!org && refresh ? <div className="dashboard-toolbar">{refresh}</div> : null}
    <p className="dashboard-environment">{query.data.development ? t("development") : t("recordedResults")}</p>
    {underway || tasks.length > 0 ? <AttentionList items={tasks} readiness={readiness} org={membership} /> : null}
    {underway ? null : <FirstSteps orgId={orgId} frameworks={query.data.frameworks} />}
    {org ? <GettingStarted org={org} readiness={readiness} /> : null}
    <FrameworkLines frameworks={query.data.frameworks} readiness={readiness} orgId={orgId} />
    {underway ? <RecordsGlance org={membership} /> : null}
  </div>;
}
