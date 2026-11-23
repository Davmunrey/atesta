"use client";

import Link from "next/link";
import { Empty, LoadError, Loading, PageHeader, Panel } from "./page-frame";
import { orgHome as homeOf } from "@/lib/org";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { isMyWorkOverdue, useMyWork } from "@/lib/api/register-hooks";
import { type Membership, orgFramework } from "@/lib/org";

/** Mi trabajo (rbac spec): what the signed-in person has to do, soonest first. */
export function MyWorkView({ org }: { org: Membership }) {
  const t = useTranslations("myWork");
  const states = useTranslations("register.states");
  const format = useFormatter();
  const english = useLocale() === "en";
  const query = useMyWork(org.organization_id);
  const today = new Date().toISOString().slice(0, 10);
  return <>
    <PageHeader crumbs={[{ label: org.organization_name, href: homeOf(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")} />
    <Panel>
    {query.isPending ? <Loading label={t("loading")} />
      : query.isError ? <LoadError error={query.error} onRetry={() => void query.refetch()} />
      : query.data.length === 0 ? <Empty>{t("empty")}</Empty>
      : <div className="table-region" role="region" aria-label={t("title")} tabIndex={0}>
        <table className="w-full text-left">
          <thead className="text-sm text-muted"><tr>
            <th scope="col">{t("measure")}</th><th scope="col">{t("framework")}</th>
            <th scope="col">{t("due")}</th><th scope="col">{t("state")}</th>
          </tr></thead>
          <tbody>
            {query.data.map((item) => {
              const overdue = isMyWorkOverdue(item, today);
              const state = item.applicability === "not_applicable" ? "not_applicable" : item.implementation ?? null;
              return <tr key={`${item.framework_key}:${item.code}`} className="border-t border-border">
                <td data-label={t("measure")} className="py-3 pr-4">
                  <Link href={`${orgFramework(org.organization_id, item.framework_key)}#req-${encodeURIComponent(item.code)}`}
                    aria-label={t("open", { code: item.code })} className="text-link underline">
                    <span className="requirement-code">{item.code}</span>
                  </Link>{" "}
                  <span lang={english && !item.title_en ? "es" : undefined}>{english ? item.title_en ?? item.title_es : item.title_es}</span>
                </td>
                <td data-label={t("framework")} className="py-3 pr-4 whitespace-nowrap">{item.framework_name}</td>
                <td data-label={t("due")} className="py-3 pr-4 whitespace-nowrap">{item.due_on ? format.dateTime(new Date(`${item.due_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) : t("noDue")}
                  {overdue ? <> <span className="requirement-state" data-state="fail">{t("overdue")}</span></> : null}</td>
                <td data-label={t("state")} className="py-3">{state ? states(state) : t("pending")}</td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>}
  </Panel></>;
}
