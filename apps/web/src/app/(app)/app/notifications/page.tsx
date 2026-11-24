"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@atesta/ui/error-message";
import { NotificationsView } from "@/components/notifications-view";
import { ApiError } from "@atesta/ui/api-error";
import { selectOrg } from "@/lib/org";
import { isContributor } from "@/lib/permissions";

export default function NotificationsPage() {
  return <Suspense><Page /></Suspense>;
}

function Page() {
  const org = selectOrg(useMe().memberships, useSearchParams().get("org"));
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  if (!isContributor(org.role)) return <ErrorMessage error={new ApiError(403, "identity.forbidden")} />;
  return <NotificationsView org={org} />;
}
