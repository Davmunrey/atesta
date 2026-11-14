"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@/components/error-message";
import { FrameworkDetailView } from "@/components/framework-detail";
import { ApiError } from "@/lib/api/hooks";
import { selectOrg } from "@/lib/org";

export default function FrameworkPage() {
  return <Suspense><FrameworkHome /></Suspense>;
}

function FrameworkHome() {
  const params = useSearchParams();
  const { memberships } = useMe();
  const org = selectOrg(memberships, params.get("org"));
  const key = params.get("framework");
  if (!org) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  if (!key) return <ErrorMessage error={new ApiError(404, "compliance.not_found")} />;
  return <FrameworkDetailView key={`${org.organization_id}:${key}`} orgId={org.organization_id} frameworkKey={key} role={org.role} />;
}
