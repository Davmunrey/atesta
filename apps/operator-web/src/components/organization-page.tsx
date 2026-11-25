"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Empty, LoadError, Loading, PageHeader } from "@atesta/ui/page-frame";
import { type OrganizationDetail, useOrganization } from "@/lib/api/organizations";
import { type StaffRole } from "@/lib/roles";
import { useStaff } from "./portal-shell";

/** A page about one organization below its detail (plan, billing details): the trail of
 *  breadcrumbs, the load states, and nothing for a role the action is not for. */
export function OrganizationPage({ title, allowed, children }: { title: string; allowed: (role: StaffRole) => boolean; children: (org: OrganizationDetail) => ReactNode }) {
  const t = useTranslations("organization");
  const list = useTranslations("organizations");
  const id = useSearchParams().get("id") ?? "";
  const staff = useStaff();
  const query = useOrganization(id);
  const crumbs = [{ label: list("title"), href: "/" }, { label: query.data?.name ?? t("crumb"), href: `/organization?id=${id}` }, { label: title }];
  return <>
    <PageHeader crumbs={crumbs} title={title} description={query.data?.name} />
    {!allowed(staff.role) ? <Empty>{t("notForRole")}</Empty>
      : query.isPending ? <Loading />
      : query.isError ? <LoadError error={query.error} onRetry={() => void query.refetch()} />
      : children(query.data)}
  </>;
}
