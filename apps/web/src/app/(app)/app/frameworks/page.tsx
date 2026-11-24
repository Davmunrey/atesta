"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@atesta/ui/error-message";
import { FrameworkLedger } from "@/components/framework-ledger";
import { LoadError, Loading, PageHeader } from "@atesta/ui/page-frame";
import { ScanHistory } from "@/components/scan-history";
import { ApiError } from "@atesta/ui/api-error";
import { useOverview } from "@/lib/api/hooks";
import { useReadiness } from "@/lib/api/register-hooks";
import { orgHome, selectOrg } from "@/lib/org";

export default function FrameworksPage() {
  return <Suspense><Frameworks /></Suspense>;
}

function Frameworks() {
  const c = useTranslations("console");
  const org = selectOrg(useMe().memberships, useSearchParams().get("org"));
  const overview = useOverview(org?.organization_id ?? "");
  const readiness = useReadiness(org?.organization_id ?? "");
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <>
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: c("frameworks") }]}
      title={c("frameworks")} description={c("frameworksPage")} />
    {overview.isError ? <LoadError error={overview.error} onRetry={() => void overview.refetch()} />
      : overview.data ? <div className="panel-grid">
        <FrameworkLedger frameworks={overview.data.frameworks} orgId={org.organization_id} readiness={readiness.data ?? []} headless />
        {/* The latest scans moved here from the home (console-unification spec). */}
        {overview.data.scans.length > 0 || overview.data.evidence_count > 0 ? <ScanHistory scans={overview.data.scans} evidenceCount={overview.data.evidence_count} /> : null}
      </div>
      : <Loading />}
  </>;
}
