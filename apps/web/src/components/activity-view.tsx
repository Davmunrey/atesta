"use client";

import { useFormatter, useTranslations } from "next-intl";
import { Empty, LoadError, Loading, PageHeader, Panel } from "@atesta/ui/page-frame";
import { orgHome as homeOf } from "@/lib/org";
import { useState } from "react";
import { useActivity } from "@/lib/api/hooks";
import type { Membership } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import { ColumnChart } from "./charts";
import { activityLabel, activityTarget } from "@/lib/activity";

const PERIODS = [30, 90] as const;
/** Days with activity before the chart says more than the table (console-unification spec). */
const CHART_MIN_DAYS = 7;

/** Who did what (insights spec): daily counts and the latest events. Admins and owners only. */
export function ActivityView({ org }: { org: Membership }) {
  const t = useTranslations("activity");
  const format = useFormatter();
  const [days, setDays] = useState<30 | 90>(30);
  const query = useActivity(org.organization_id, days);
  if (!canReviewControls(org.role)) return <p className="text-muted">{t("adminsOnly")}</p>;
  return <div className="activity-page panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: homeOf(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")}
      actions={<div role="group" aria-label={t("period")} className="requirement-filters">
        {PERIODS.map((d) => <button key={d} type="button" className="dashboard-button" aria-pressed={days === d} onClick={() => setDays(d)}>{t("lastDays", { days: d })}</button>)}
      </div>} />
    {query.isPending ? <Loading label={t("loading")} />
      : query.isError ? <LoadError error={query.error} onRetry={() => void query.refetch()} />
      : <div className={`panel-grid${query.isFetching ? " is-refetching" : ""}`}>
        {query.data.daily.filter((d) => d.count > 0).length < CHART_MIN_DAYS ? null : <Panel><ColumnChart title={t("perDay")} periodLabel={t("day")} valueLabel={t("events")} tableLabel={t("showTable")}
          points={query.data.daily.map((d) => ({ label: format.dateTime(new Date(`${d.day}T00:00:00`), { day: "numeric", month: "short" }), value: d.count }))} /></Panel>}
        <Panel title={t("latest")}>
        {query.data.events.length === 0 ? <Empty>{t("empty")}</Empty> : <div className="table-region" role="region" aria-label={t("latest")} tabIndex={0}><table className="activity-table">
          <thead><tr><th scope="col">{t("when")}</th><th scope="col">{t("who")}</th><th scope="col">{t("what")}</th></tr></thead>
          <tbody>{query.data.events.map((e, i) => <tr key={`${e.occurred_at}-${i}`}>
            <td data-label={t("when")}><time dateTime={e.occurred_at}>{format.dateTime(new Date(e.occurred_at), { dateStyle: "medium", timeStyle: "short" })}</time></td>
            <td data-label={t("who")}>{e.actor_kind === "atesta" ? t("actor.atesta") : e.actor_email ?? t("system")}</td>
            <td data-label={t("what")}>{activityLabel(t, e.action)}{activityTarget(e.target_id) ? <span className="activity-target">{activityTarget(e.target_id)}</span> : null}</td>
          </tr>)}</tbody>
        </table></div>}
        </Panel>
      </div>}
  </div>;
}
