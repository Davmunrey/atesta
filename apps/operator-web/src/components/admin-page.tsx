"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Empty, PageHeader } from "@atesta/ui/page-frame";
import { isAdmin } from "@/lib/roles";
import { useStaff } from "./portal-shell";

/** An admin-only screen (team, operations log, erased organizations): nothing for other roles. */
export function AdminPage({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  const t = useTranslations("organization");
  return <>
    <PageHeader title={title} description={description} />
    {isAdmin(useStaff().role) ? children : <Empty>{t("notForRole")}</Empty>}
  </>;
}
