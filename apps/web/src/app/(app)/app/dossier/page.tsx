"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { DossierView } from "@/components/dossier-view";
import { ErrorMessage } from "@/components/error-message";
import { ApiError } from "@/lib/api/hooks";
import { selectOrg } from "@/lib/org";

export default function DossierPage() {
  return <Suspense><Page /></Suspense>;
}

function Page() {
  const params = useSearchParams();
  const org = selectOrg(useMe().memberships, params.get("org"));
  const framework = params.get("framework");
  if (org === null || !framework) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <DossierView org={org} frameworkKey={framework} />;
}
