"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@atesta/ui/error-message";
import { IncidentView } from "@/components/incident-view";
import { ApiError } from "@atesta/ui/api-error";
import { selectOrg } from "@/lib/org";

export default function IncidentPage() {
  return <Suspense><Page /></Suspense>;
}

function Page() {
  const params = useSearchParams();
  const org = selectOrg(useMe().memberships, params.get("org"));
  const id = params.get("id");
  if (org === null || !id) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <IncidentView org={org} incidentId={id} />;
}
