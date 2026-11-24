"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useEffect, useState } from "react";
import { useMe } from "@/components/auth-gate";
import { ConnectionsView } from "@/components/connections-view";
import { ErrorMessage } from "@/components/error-message";
import { ApiError } from "@/lib/api/hooks";
import { orgConnections, selectOrg } from "@/lib/org";
import { isContributor } from "@/lib/permissions";

export default function ConnectionsPage() {
  return <Suspense><Page /></Suspense>;
}

/** web-connections spec: the consent callback lands here with `connection` or `error`. */
function Page() {
  const t = useTranslations("connections");
  const params = useSearchParams();
  const { memberships } = useMe();
  const requested = params.get("org") ?? (memberships.length === 1 ? memberships[0]?.organization_id ?? null : null);
  const org = selectOrg(memberships, requested);
  // Read once, then dropped from the address bar: a reload must not repeat the notice.
  const [{ focus, error }] = useState(() => ({ focus: params.get("connection"), error: params.get("error") }));
  useEffect(() => {
    if (org !== null && (params.has("connection") || params.has("error"))) window.history.replaceState(null, "", orgConnections(org.organization_id));
  }, [org, params]);
  if (org === null) {
    return error !== null
      ? <div className="panel-grid"><ErrorMessage error={new ApiError(400, error)} /><p><Link href="/app">{t("chooseOrg")}</Link></p></div>
      : <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  }
  if (!isContributor(org.role)) return <ErrorMessage error={new ApiError(403, "identity.forbidden")} />;
  return <ConnectionsView org={org} focus={focus} error={error} />;
}
