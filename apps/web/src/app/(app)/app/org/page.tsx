"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@atesta/ui/error-message";
import { ApiError } from "@atesta/ui/api-error";
import { OverviewDashboard } from "@/components/overview-dashboard";
import { selectOrg } from "@/lib/org";

// Static export: the org id travels in the query string, read on the client.
export default function OrgPage() {
  return (
    <Suspense>
      <OrgHome />
    </Suspense>
  );
}

function OrgHome() {
  const { memberships } = useMe();
  const org = selectOrg(memberships, useSearchParams().get("org"));
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <section className="overview-page"><OverviewDashboard key={org.organization_id} orgId={org.organization_id} org={org} /></section>;
}
