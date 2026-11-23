"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { useActivity } from "@/lib/api/hooks";
import type { Membership } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import { ColumnChart } from "./charts";
import { ErrorMessage } from "./error-message";

const PERIODS = [30, 90] as const;

/** Who did what (insights spec): daily counts and the latest events. Admins and owners only. */
export function ActivityView({ org }: { org: Membership }) {
  const t = useTranslations("activity");
  const format = useFormatter();
  const [days, setDays] = useState<30 | 90>(30);
  const query = useActivity(org.organization_id, days);
  if (!canReviewControls(org.role)) return <p className="text-muted">{t("adminsOnly")}</p>;
  // Message keys cannot hold dots, so "requirement.assessed" is stored as "requirement_assessed".
  const action = (name: string) => { const key = `actions.${name.replaceAll(".", "_")}`; return t.has(key) ? t(key) : name; };
  return <section className="activity-page" aria-labelledby="activity-heading">
    <h1 id="activity-heading" className="page-title">{t("title")}</h1>
    <p className="text-muted">{t("intro")}</p>
    <div role="group" aria-label={t("period")} className="requirement-filters">
      {PERIODS.map((d) => <button key={d} type="button" className="dashboard-button" aria-pressed={days === d} onClick={() => setDays(d)}>{t("lastDays", { days: d })}</button>)}
    </div>
    {query.isPending ? <div className="dashboard-loading" role="status" aria-busy="true"><p>{t("loading")}</p></div>
      : query.isError ? <ErrorMessage error={query.error} />
      : <div className={query.isFetching ? "is-refetching" : undefined}>
        <ColumnChart title={t("perDay")} valueLabel={t("events")} tableLabel={t("showTable")}
          points={query.data.daily.map((d) => ({ label: format.dateTime(new Date(`${d.day}T00:00:00`), { day: "numeric", month: "short" }), value: d.count }))} />
        <h2 className="activity-subtitle">{t("latest")}</h2>
        {query.data.events.length === 0 ? <p className="text-muted">{t("empty")}</p> : <div className="table-region" role="region" aria-label={t("latest")} tabIndex={0}><table className="activity-table">
          <thead><tr><th scope="col">{t("when")}</th><th scope="col">{t("who")}</th><th scope="col">{t("what")}</th></tr></thead>
          <tbody>{query.data.events.map((e, i) => <tr key={`${e.occurred_at}-${i}`}>
            <td><time dateTime={e.occurred_at}>{format.dateTime(new Date(e.occurred_at), { dateStyle: "medium", timeStyle: "short" })}</time></td>
            <td>{e.actor_email ?? t("system")}</td>
            <td>{action(e.action)}<span className="activity-target">{e.target_id}</span></td>
          </tr>)}</tbody>
        </table></div>}
      </div>}
  </section>;
}
