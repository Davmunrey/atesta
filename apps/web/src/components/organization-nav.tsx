"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useId } from "react";
import { orgActivity, orgHome, orgInvitations, orgMembers, orgMyWork, selectOrg } from "@/lib/org";
import { canInvite, canReviewControls, isContributor } from "@/lib/permissions";
import { useMe } from "./auth-gate";

export function OrganizationNav() {
  const t = useTranslations("org");
  const format = useFormatter();
  const { memberships } = useMe();
  const pathname = usePathname();
  const router = useRouter();
  const switcherId = useId();
  const org = selectOrg(memberships, useSearchParams().get("org"));
  if (!org || !["/app/org", "/app/framework", "/app/members", "/app/invitations", "/app/activity", "/app/my-work"].includes(pathname)) return null;

  function switchOrganization(id: string) {
    const next = selectOrg(memberships, id);
    if (!next) return;
    const destination = pathname === "/app/members" && isContributor(next.role) ? orgMembers
      : pathname === "/app/my-work" && isContributor(next.role) ? orgMyWork
      : pathname === "/app/invitations" && canInvite(next.role) ? orgInvitations : orgHome;
    router.push(destination(id));
  }

  const sections = [
    { label: t("overview"), href: orgHome(org.organization_id) },
    ...(isContributor(org.role) ? [
      { label: t("myWork"), href: orgMyWork(org.organization_id) },
      { label: t("members"), href: orgMembers(org.organization_id) },
    ] : []),
    ...(canInvite(org.role) ? [{ label: t("invitations"), href: orgInvitations(org.organization_id) }] : []),
    ...(canReviewControls(org.role) ? [{ label: t("activity"), href: orgActivity(org.organization_id) }] : []),
  ];
  return (
    <aside className="organization-context">
      {memberships.length > 1 ? <>
        <label htmlFor={switcherId} className="text-sm text-muted">{t("switcher")}</label>
        <select id={switcherId} value={org.organization_id} onChange={(event) => switchOrganization(event.target.value)}
          className="organization-switcher">
          {memberships.map((membership) => (
            <option key={membership.organization_id} value={membership.organization_id}>{membership.organization_name}</option>
          ))}
        </select>
      </> : <p className="organization-name">{org.organization_name}</p>}
      {org.access_expires_on ? <p className="framework-notice" role="note">
        {t("auditorUntil", { date: format.dateTime(new Date(`${org.access_expires_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) })}
      </p> : null}
      <nav aria-label={t("sections")} className="organization-nav">
        {sections.map(({ label, href }) => (
          <Link key={href} href={href} aria-current={href.split("?")[0] === (pathname === "/app/framework" ? "/app/org" : pathname) ? "page" : undefined}>
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
