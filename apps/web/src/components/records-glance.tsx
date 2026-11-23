"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { UseQueryResult } from "@tanstack/react-query";
import { useAccessReviews, useIncidents, usePolicies, useTrainingCampaigns } from "@/lib/api/routines";
import { type Membership, orgAccessReviews, orgIncidents, orgPolicies, orgTraining } from "@/lib/org";
import { incidentSummary, overdueTrainings, policySummary, reviewSummary, trainingSummary } from "@/lib/summaries";
import { Icon } from "./icons";
import { Panel } from "./page-frame";

type Row = { name: string; href: string; query: UseQueryResult<unknown[]>; empty: string; read: () => { attention: boolean; lead: string } };

/** Records at a glance (ui-polish spec, issue 287): the records an auditor asks for, in a fixed
 *  order, each with its state written out and the sentence its own page leads with. */
export function RecordsGlance({ org }: { org: Membership }) {
  const t = useTranslations("summary");
  const r = useTranslations("routines");
  const kpi = useTranslations("console.kpi");
  const app = useTranslations("app");
  const id = org.organization_id;
  const today = new Date().toISOString().slice(0, 10);
  const policies = usePolicies(id);
  const reviews = useAccessReviews(id);
  const training = useTrainingCampaigns(id);
  const incidents = useIncidents(id);
  const rows: Row[] = [
    { name: r("policies.title"), href: orgPolicies(id), query: policies, empty: r("policies.empty"), read: () => {
      const s = policySummary(policies.data ?? [], today);
      return { attention: s.overdue + s.unapproved > 0, lead: t("policies.lead", { attention: s.overdue + s.unapproved }) };
    } },
    { name: r("access.title"), href: orgAccessReviews(id), query: reviews, empty: r("access.empty"), read: () => {
      const s = reviewSummary(reviews.data ?? [], today);
      return { attention: s.late > 0, lead: t("access.lead", { open: s.open, pending: s.pending }) };
    } },
    { name: r("training.title"), href: orgTraining(id), query: training, empty: r("training.empty"), read: () => {
      const s = trainingSummary(training.data ?? []);
      return { attention: overdueTrainings(training.data ?? [], today) > 0, lead: t("training.lead", { open: s.open, acknowledged: s.acknowledged }) };
    } },
    { name: r("incidents.title"), href: orgIncidents(id), query: incidents, empty: r("incidents.empty"), read: () => {
      const s = incidentSummary(incidents.data ?? []);
      return { attention: s.overdue > 0, lead: t("incidents.lead", { open: s.open, overdue: s.overdue }) };
    } },
  ];
  return <Panel title={t("glance.title")} description={t("glance.help")}>
    <div className="table-region" role="region" aria-label={t("glance.title")} tabIndex={0}><table className="w-full text-left records-glance" aria-label={t("glance.title")}>
      <thead><tr><th scope="col">{t("glance.record")}</th><th scope="col">{t("glance.state")}</th><th scope="col">{t("glance.summary")}</th></tr></thead>
      <tbody>{rows.map((row) => {
        const state = row.query.isPending || row.query.isError ? null : row.query.data.length === 0 ? "empty" : row.read();
        return <tr key={row.href}>
          <th scope="row"><Link href={row.href} className="text-link underline">{row.name}</Link></th>
          <td data-label={t("glance.state")}>{state === null ? "—" : state === "empty"
            ? <span className="badge" data-severity="pending"><Icon name="pending" />{t("glance.none")}</span>
            : <span className="badge" data-severity={state.attention ? "overdue" : "done"}><Icon name={state.attention ? "overdue" : "done"} />{kpi(state.attention ? "act" : "clear")}</span>}</td>
          <td data-label={t("glance.summary")} className={state && state !== "empty" ? undefined : "text-muted"}>
            {row.query.isPending ? app("loading") : row.query.isError ? t("glance.failed") : state === "empty" ? row.empty : state?.lead}</td>
        </tr>;
      })}</tbody>
    </table></div>
  </Panel>;
}
