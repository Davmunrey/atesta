"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useId } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@/components/error-message";
import { ApiError } from "@/lib/api/hooks";
import Link from "next/link";
import { orgHome, orgInvitations, orgMembers, selectOrg } from "@/lib/org";
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
  const router = useRouter();
  const switcherId = useId();
  const { memberships } = useMe();
  const org = selectOrg(memberships, useSearchParams().get("org"));
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <label htmlFor={switcherId} className="text-sm text-muted">
          {t("org.switcher")}
        </label>
        <select
          id={switcherId}
          value={org.organization_id}
          onChange={(event) => router.push(orgHome(event.target.value))}
          className="rounded-md border border-border bg-bg px-2 py-1"
        >
          {memberships.map((m) => (
            <option key={m.organization_id} value={m.organization_id}>
              {m.organization_name}
            </option>
          ))}
        </select>
      </div>
      <h1 className="text-2xl font-semibold">{org.organization_name}</h1>
      <p className="text-muted">{t("org.yourRole", { role: t(`roles.${org.role}`) })}</p>
      <nav aria-label={t("org.sections")} className="flex gap-4">
        <Link href={orgMembers(org.organization_id)} className="underline">
          {t("org.members")}
        </Link>
        {canInvite(org.role) ? (
          <Link href={orgInvitations(org.organization_id)} className="underline">
            {t("org.invitations")}
          </Link>
        ) : null}
      </nav>
    </section>
  );
}
