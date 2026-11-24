"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { AccessReviewView } from "@/components/access-review-view";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@atesta/ui/error-message";
import { ApiError } from "@atesta/ui/api-error";
import { selectOrg } from "@/lib/org";

export default function AccessReviewPage() {
  return <Suspense><Page /></Suspense>;
}

function Page() {
  const params = useSearchParams();
  const org = selectOrg(useMe().memberships, params.get("org"));
  const id = params.get("id");
  if (org === null || !id) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <AccessReviewView org={org} reviewId={id} />;
}
