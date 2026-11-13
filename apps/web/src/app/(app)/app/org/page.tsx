"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@/components/error-message";
import { ApiError } from "@/lib/api/hooks";
import Link from "next/link";
import { orgInvitations, orgMembers, selectOrg } from "@/lib/org";
import { canInvite } from "@/lib/permissions";

// Static export: the org id travels in the query string, read on the client.
export default function OrgPage() {
  return (
    <Suspense>
      <OrgHome />
    </Suspense>
  );
}

function OrgHome() {
  const t = useTranslations();
  const { memberships } = useMe();
  const org = selectOrg(memberships, useSearchParams().get("org"));
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return (
    <section className="flex flex-col gap-4">
      <h1 className="page-title">{org.organization_name}</h1>
      <p className="text-muted">{t("org.yourRole", { role: t(`roles.${org.role}`) })}</p>
      <div className="section-links">
        <Link href={orgMembers(org.organization_id)}>
          <span className="section-link-title">{t("org.members")}</span>
          <span className="text-sm text-muted">{t("org.membersHelp")}</span>
        </Link>
        {canInvite(org.role) ? (
          <Link href={orgInvitations(org.organization_id)}>
            <span className="section-link-title">{t("org.invitations")}</span>
            <span className="text-sm text-muted">{t("org.invitationsHelp")}</span>
          </Link>
        ) : null}
      </div>
    </section>
  );
}
