"use client";

import { useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { api } from "@/lib/api/client";
import { unwrap } from "@atesta/ui/api-error";
import type { Readiness } from "@/lib/api/register-hooks";
import type { DueItem } from "@/lib/api/routines";
import { type Membership, orgHome } from "@/lib/org";
import type { ReactNode } from "react";
import { Badge } from "@atesta/ui/badge";
import { PageHeader, Panel } from "@atesta/ui/page-frame";

type Row = {
  org: Membership;
  ready: boolean;
  failed: boolean;
  started: number;
  assessed: number;
  total: number;
  overdue: number;
  pending: number;
  pendingOverdue: number;
  last: string | null;
};

function toRow(org: Membership, readiness: Readiness[] | undefined, due: DueItem[] | undefined, failed: boolean): Row {
  const frameworks = readiness ?? [];
  const dates = frameworks.map((f) => f.last_assessed_at).filter((d): d is string => !!d).sort();
  const inProgress = frameworks.filter((f) => f.assessed > 0); // untouched frameworks would inflate the total
  return {
    org, failed, ready: readiness !== undefined && due !== undefined,
    started: inProgress.length,
    assessed: inProgress.reduce((n, f) => n + f.assessed, 0),
    total: inProgress.reduce((n, f) => n + f.total, 0),
    overdue: frameworks.reduce((n, f) => n + f.overdue, 0),
    pending: (due ?? []).length,
    pendingOverdue: (due ?? []).filter((d) => d.overdue).length,
    last: dates.at(-1) ?? null,
  };
}

/** Most urgent first: overdue measures and routines, then pending routines, then by name. */
export function byUrgency(a: Row, b: Row): number {
  return (b.overdue + b.pendingOverdue) - (a.overdue + a.pendingOverdue)
    || b.pending - a.pending
    || a.org.organization_name.localeCompare(b.org.organization_name);
}

/**
 * The portfolio (consultancy-portfolio spec). Each organization is read through its own endpoints,
 * in its own tenant context, so there is no cross-tenant query (ADR-012). Counts only (ADR-005).
 */
export function Portfolio({ memberships, actions }: { memberships: Membership[]; actions?: ReactNode }) {
  const t = useTranslations("portfolio");
  const r = useTranslations("roles");
  const format = useFormatter();
  const readiness = useQueries({
    queries: memberships.map((m) => ({
      queryKey: ["readiness", m.organization_id], retry: false,
      queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/readiness", { params: { path: { org_id: m.organization_id } } })),
    })),
  });
  const due = useQueries({
    queries: memberships.map((m) => ({
      queryKey: ["routines-due", m.organization_id], retry: false,
      queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/routines/due", { params: { path: { org_id: m.organization_id } } })),
    })),
  });
  const rows = memberships
    .map((m, i) => toRow(m, readiness[i]?.data, due[i]?.data, !!(readiness[i]?.isError || due[i]?.isError)))
    .sort(byUrgency);
  const loaded = rows.filter((x) => x.ready);
  const withOverdue = loaded.filter((x) => x.overdue + x.pendingOverdue > 0).length;
  const notStarted = loaded.filter((x) => x.started === 0).length;
  // On the console page grid: the page header, then the register in a panel (console-unification spec).
  return <div className="panel-grid">
    <PageHeader title={t("title")} actions={actions} description={<ul className="portfolio-summary" aria-label={t("summary")}>
      <li>{t("organizations", { count: memberships.length })}</li>
      <li data-severity={withOverdue > 0 ? "overdue" : undefined}>{t("withOverdue", { count: withOverdue })}</li>
      <li>{t("notStarted", { count: notStarted })}</li>
    </ul>} />
    <Panel><div className="table-region" role="region" aria-label={t("title")} tabIndex={0}><table className="w-full text-left">
      <thead><tr>
        <th scope="col">{t("organization")}</th><th scope="col">{t("assessed")}</th><th scope="col">{t("overdue")}</th>
        <th scope="col">{t("routines")}</th><th scope="col">{t("lastAssessed")}</th>
      </tr></thead>
      <tbody>{rows.map((x) => <tr key={x.org.organization_id}>
        <td data-label={t("organization")}><Link href={orgHome(x.org.organization_id)} className="text-link underline">{x.org.organization_name}</Link>
          <span className="block text-sm text-muted">{r(x.org.role)} · {t("frameworks", { count: x.started })}</span></td>
        {x.failed ? <td colSpan={4} data-label={t("assessed")} className="text-muted">{t("failed")}</td>
          : !x.ready ? <td colSpan={4} data-label={t("assessed")} className="text-muted">{t("loading")}</td>
          : <>
            <td data-label={t("assessed")} className="tabular-nums">{x.started === 0 ? t("notStartedCell") : t("ofTotal", { assessed: x.assessed, total: x.total })}</td>
            <td data-label={t("overdue")} className="tabular-nums">{x.overdue > 0 ? <Badge state="measureOverdue">{format.number(x.overdue)}</Badge> : format.number(0)}</td>
            <td data-label={t("routines")} className="tabular-nums">{x.pending === 0 ? t("noRoutines") : x.pendingOverdue > 0 ? t("pendingWithOverdue", { count: x.pending, overdue: x.pendingOverdue }) : t("pending", { count: x.pending })}</td>
            <td data-label={t("lastAssessed")} className="tabular-nums">{x.last ? format.dateTime(new Date(x.last), { dateStyle: "medium" }) : t("never")}</td>
          </>}
      </tr>)}</tbody>
    </table></div></Panel>
  </div>;
}
