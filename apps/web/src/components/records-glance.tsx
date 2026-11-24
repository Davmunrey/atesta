"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { UseQueryResult } from "@tanstack/react-query";
import { useAccessReviews, useIncidents, usePolicies, useTrainingCampaigns } from "@/lib/api/routines";
import { type Membership, orgAccessReviews, orgIncidents, orgPolicies, orgTraining } from "@/lib/org";
import { Badge } from "./badge";
import { Panel } from "./page-frame";
import { RecordBadge, type RecordState, useRecordSentence, useRecordStates } from "./record-summary";

type Row = { name: string; href: string; query: UseQueryResult<unknown[]>; empty: string; read: () => RecordState };

/** Records at a glance (ui-polish spec, issue 287): the records an auditor asks for, in a fixed
 *  order, each with the badge and the sentence its own page leads with (console-unification spec). */
export function RecordsGlance({ org }: { org: Membership }) {
  const t = useTranslations("summary");
  const r = useTranslations("routines");
  const app = useTranslations("app");
  const states = useRecordStates();
  const sentence = useRecordSentence();
  const id = org.organization_id;
  const policies = usePolicies(id);
  const reviews = useAccessReviews(id);
  const training = useTrainingCampaigns(id);
  const incidents = useIncidents(id);
  const rows: Row[] = [
    { name: r("policies.title"), href: orgPolicies(id), query: policies, empty: r("policies.empty"), read: () => states.policies(policies.data ?? []) },
    { name: r("access.title"), href: orgAccessReviews(id), query: reviews, empty: r("access.empty"), read: () => states.access(reviews.data ?? []) },
    { name: r("training.title"), href: orgTraining(id), query: training, empty: r("training.empty"), read: () => states.training(training.data ?? []) },
    { name: r("incidents.title"), href: orgIncidents(id), query: incidents, empty: r("incidents.empty"), read: () => states.incidents(incidents.data ?? []) },
  ];
  return <Panel title={t("glance.title")} description={t("glance.help")}>
    <div className="table-region" role="region" aria-label={t("glance.title")} tabIndex={0}><table className="w-full text-left records-glance" aria-label={t("glance.title")}>
      <thead><tr><th scope="col">{t("glance.record")}</th><th scope="col">{t("glance.state")}</th><th scope="col">{t("glance.summary")}</th></tr></thead>
      <tbody>{rows.map((row) => {
        const state = row.query.isPending || row.query.isError ? null : row.query.data.length === 0 ? "empty" : row.read();
        return <tr key={row.href}>
          <th scope="row"><Link href={row.href} className="text-link underline">{row.name}</Link></th>
          <td data-label={t("glance.state")}>{state === null ? "—" : state === "empty" ? <Badge severity="pending">{t("glance.none")}</Badge> : <RecordBadge state={state} />}</td>
          <td data-label={t("glance.summary")} className={state && state !== "empty" ? undefined : "text-muted"}>
            {row.query.isPending ? app("loading") : row.query.isError ? t("glance.failed") : state === "empty" ? row.empty : state ? sentence(state) : null}</td>
        </tr>;
      })}</tbody>
    </table></div>
  </Panel>;
}
