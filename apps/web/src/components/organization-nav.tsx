"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useId } from "react";
import { orgHome, orgInvitations, orgMembers, selectOrg } from "@/lib/org";
import { canInvite } from "@/lib/permissions";
import { useMe } from "./auth-gate";

export function OrganizationNav() {
  const t = useTranslations("org");
  const { memberships } = useMe();
  const pathname = usePathname();
  const router = useRouter();
  const switcherId = useId();
  const org = selectOrg(memberships, useSearchParams().get("org"));
  if (!org || !["/app/org", "/app/members", "/app/invitations"].includes(pathname)) return null;

  function switchOrganization(id: string) {
    const next = selectOrg(memberships, id);
    if (!next) return;
    const destination = pathname === "/app/members" ? orgMembers
      : pathname === "/app/invitations" && canInvite(next.role) ? orgInvitations : orgHome;
    router.push(destination(id));
  }

  const sections = [
    { label: t("overview"), href: orgHome(org.organization_id) },
    { label: t("members"), href: orgMembers(org.organization_id) },
    ...(canInvite(org.role) ? [{ label: t("invitations"), href: orgInvitations(org.organization_id) }] : []),
  ];
  return (
    <aside className="organization-context">
      <label htmlFor={switcherId} className="text-sm text-muted">{t("switcher")}</label>
      <select id={switcherId} value={org.organization_id} onChange={(event) => switchOrganization(event.target.value)}
        className="organization-switcher">
        {memberships.map((membership) => (
          <option key={membership.organization_id} value={membership.organization_id}>{membership.organization_name}</option>
        ))}
      </select>
      <nav aria-label={t("sections")} className="organization-nav">
        {sections.map(({ label, href }) => (
          <Link key={href} href={href} aria-current={href.split("?")[0] === pathname ? "page" : undefined}>
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
