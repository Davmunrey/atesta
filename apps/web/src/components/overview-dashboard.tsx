"use client";

import { useTranslations } from "next-intl";
import { useOverview } from "@/lib/api/hooks";
import { ErrorMessage } from "./error-message";
import { FirstSteps } from "./first-steps";
import { FrameworkLedger } from "./framework-ledger";
import { ScanHistory } from "./scan-history";

export function OverviewDashboard({ orgId }: { orgId: string }) {
  const t = useTranslations("dashboard");
  const query = useOverview(orgId);
  if (query.isPending) return <div className="dashboard-loading" role="status" aria-busy="true">
    <p>{t("loading")}</p><div className="dashboard-skeleton" aria-hidden="true" /><div className="dashboard-skeleton" aria-hidden="true" />
  </div>;
  if (query.isError) return <div className="dashboard-error"><ErrorMessage error={query.error} /><button className="dashboard-button" onClick={() => void query.refetch()}>{t("retry")}</button></div>;
  return <div className="dashboard">
    <div className="dashboard-toolbar">
      <p>{query.data.development ? t("development") : t("recordedResults")}</p>
      {query.data.frameworks.some((f) => f.snapshot) || query.data.scans.length > 0
        ? <button className="dashboard-button" disabled={query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? t("refreshing") : t("refresh")}</button> : null}
    </div>
    <FirstSteps orgId={orgId} frameworks={query.data.frameworks} />
    <div className="dashboard-grid">
      <FrameworkLedger key={orgId} frameworks={query.data.frameworks} orgId={orgId} />
      <ScanHistory scans={query.data.scans} evidenceCount={query.data.evidence_count} />
    </div>
    <p className="dashboard-note">{t("assessmentNote")}</p>
  </div>;
}
