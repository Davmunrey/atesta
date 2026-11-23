"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@/components/error-message";
import { PoliciesView } from "@/components/policies-view";
import { ApiError } from "@/lib/api/hooks";
import { selectOrg } from "@/lib/org";

export default function PoliciesPage() {
  return <Suspense><Page /></Suspense>;
}

function Page() {
  const org = selectOrg(useMe().memberships, useSearchParams().get("org"));
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <PoliciesView org={org} />;
}
