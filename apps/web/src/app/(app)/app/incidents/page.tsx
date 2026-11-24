"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@atesta/ui/error-message";
import { IncidentsView } from "@/components/incidents-view";
import { ApiError } from "@atesta/ui/api-error";
import { selectOrg } from "@/lib/org";

export default function IncidentsPage() {
  return <Suspense><Page /></Suspense>;
}

function Page() {
  const org = selectOrg(useMe().memberships, useSearchParams().get("org"));
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <IncidentsView org={org} />;
}
