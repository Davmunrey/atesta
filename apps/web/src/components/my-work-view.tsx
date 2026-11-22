"use client";

import Link from "next/link";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { isMyWorkOverdue, useMyWork } from "@/lib/api/register-hooks";
import { type Membership, orgFramework } from "@/lib/org";
import { ErrorMessage } from "./error-message";

/** Mi trabajo (rbac spec): what the signed-in person has to do, soonest first. */
export function MyWorkView({ org }: { org: Membership }) {
  const t = useTranslations("myWork");
  const states = useTranslations("register.states");
  const format = useFormatter();
  const english = useLocale() === "en";
  const query = useMyWork(org.organization_id);
  const today = new Date().toISOString().slice(0, 10);
  return <section className="flex flex-col gap-4">
    <div><h1 className="page-title">{t("title")}</h1><p className="text-muted">{t("intro")}</p></div>
    {query.isPending ? <p role="status">{t("loading")}</p>
      : query.isError ? <ErrorMessage error={query.error} />
      : query.data.length === 0 ? <p className="text-muted">{t("empty")}</p>
      : <div className="table-region" role="region" aria-label={t("title")} tabIndex={0}>
        <table className="w-full text-left max-sm:block max-sm:min-w-0">
          <thead className="text-sm text-muted max-sm:hidden"><tr>
            <th scope="col">{t("measure")}</th><th scope="col">{t("framework")}</th>
            <th scope="col">{t("due")}</th><th scope="col">{t("state")}</th>
          </tr></thead>
          <tbody className="max-sm:block">
            {query.data.map((item) => {
              const overdue = isMyWorkOverdue(item, today);
              const state = item.applicability === "not_applicable" ? "not_applicable" : item.implementation ?? null;
              return <tr key={`${item.framework_key}:${item.code}`} className="border-t border-border max-sm:block max-sm:py-3">
                <td className="py-3 pr-4 max-sm:block max-sm:p-0">
                  <Link href={`${orgFramework(org.organization_id, item.framework_key)}#req-${encodeURIComponent(item.code)}`}
                    aria-label={t("open", { code: item.code })} className="text-link underline">
                    <span className="requirement-code">{item.code}</span>
                  </Link>{" "}
                  <span lang={english && !item.title_en ? "es" : undefined}>{english ? item.title_en ?? item.title_es : item.title_es}</span>
                </td>
                <td className="py-3 pr-4 whitespace-nowrap max-sm:block max-sm:p-0 max-sm:text-sm max-sm:text-muted">{item.framework_name}</td>
                <td className="py-3 pr-4 whitespace-nowrap max-sm:inline-block max-sm:p-0 max-sm:pr-3 max-sm:text-sm">{item.due_on ? format.dateTime(new Date(`${item.due_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) : t("noDue")}
                  {overdue ? <> <span className="requirement-state" data-state="fail">{t("overdue")}</span></> : null}</td>
                <td className="py-3 max-sm:inline-block max-sm:p-0 max-sm:text-sm">{state ? states(state) : t("pending")}</td>
              </tr>;
            })}
          </tbody>
        </table>
      </div>}
  </section>;
}
