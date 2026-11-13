"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@/components/error-message";
import { MembersView } from "@/components/members-view";
import { ApiError } from "@/lib/api/hooks";
import { selectOrg } from "@/lib/org";

export default function MembersPage() {
  return (
    <Suspense>
      <Members />
    </Suspense>
  );
}

function Members() {
  const org = selectOrg(useMe().memberships, useSearchParams().get("org"));
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <MembersView org={org} />;
}
