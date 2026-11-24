"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { api } from "@/lib/api/client";
import { unwrap } from "@atesta/ui/api-error";
import type { components } from "@/lib/api/schema";
import { type Membership, orgHome } from "@/lib/org";
import type { ReactNode } from "react";
import { Badge } from "@atesta/ui/badge";
import { PageHeader, Panel } from "@atesta/ui/page-frame";

type Summary = components["schemas"]["PortfolioSummary"];
type Row = { id: string; name: string; role: Membership["role"]; summary: Summary | null };

/**
 * The portfolio (consultancy-portfolio spec). One request returns every organization, most urgent
 * first: the API reads each one in its own tenant context, so there is no cross-tenant query
 * (ADR-012 amendment 10, issue 228). Counts only (ADR-005).
 */
export function Portfolio({ memberships, actions }: { memberships: Membership[]; actions?: ReactNode }) {
  const t = useTranslations("portfolio");
  const r = useTranslations("roles");
  const format = useFormatter();
  const portfolio = useQuery({ queryKey: ["portfolio"], retry: false, queryFn: () => unwrap(api.GET("/api/v1/portfolio")) });
  // Until the answer arrives, the organizations the session already knows, each one loading.
  const rows: Row[] = portfolio.data
    ? portfolio.data.rows.map((x) => ({ id: x.organization_id, name: x.organization_name, role: x.role, summary: x.summary }))
    : memberships.map((m) => ({ id: m.organization_id, name: m.organization_name, role: m.role, summary: null }));
  const loaded = rows.flatMap((x) => (x.summary ? [x.summary] : []));
  const withOverdue = loaded.filter((x) => x.overdue + x.pending_overdue > 0).length;
  const notStarted = loaded.filter((x) => x.frameworks_in_progress === 0).length;
  const notShown = portfolio.data?.not_shown ?? 0;
  // On the console page grid: the page header, then the register in a panel (console-unification spec).
  return <div className="panel-grid">
    <PageHeader title={t("title")} actions={actions} description={<ul className="portfolio-summary" aria-label={t("summary")}>
      <li>{t("organizations", { count: rows.length + notShown })}</li>
      <li data-severity={withOverdue > 0 ? "overdue" : undefined}>{t("withOverdue", { count: withOverdue })}</li>
      <li>{t("notStarted", { count: notStarted })}</li>
      {notShown > 0 && <li>{t("notShown", { count: notShown })}</li>}
    </ul>} />
    <Panel><div className="table-region" role="region" aria-label={t("title")} tabIndex={0}><table className="w-full text-left">
      <thead><tr>
        <th scope="col">{t("organization")}</th><th scope="col">{t("assessed")}</th><th scope="col">{t("overdue")}</th>
        <th scope="col">{t("routines")}</th><th scope="col">{t("lastAssessed")}</th>
      </tr></thead>
      <tbody>{rows.map(({ id, name, role, summary: x }) => <tr key={id}>
        <td data-label={t("organization")}><Link href={orgHome(id)} className="text-link underline">{name}</Link>
          <span className="block text-sm text-muted">{r(role)} · {t("frameworks", { count: x?.frameworks_in_progress ?? 0 })}</span></td>
        {!x ? <td colSpan={4} data-label={t("assessed")} className="text-muted">{portfolio.isPending ? t("loading") : t("failed")}</td>
          : <>
            <td data-label={t("assessed")} className="tabular-nums">{x.frameworks_in_progress === 0 ? t("notStartedCell") : t("ofTotal", { assessed: x.assessed, total: x.total })}</td>
            <td data-label={t("overdue")} className="tabular-nums">{x.overdue > 0 ? <Badge state="measureOverdue">{format.number(x.overdue)}</Badge> : format.number(0)}</td>
            <td data-label={t("routines")} className="tabular-nums">{x.pending === 0 ? t("noRoutines") : x.pending_overdue > 0 ? t("pendingWithOverdue", { count: x.pending, overdue: x.pending_overdue }) : t("pending", { count: x.pending })}</td>
            <td data-label={t("lastAssessed")} className="tabular-nums">{x.last_assessed_at ? format.dateTime(new Date(x.last_assessed_at), { dateStyle: "medium" }) : t("never")}</td>
          </>}
      </tr>)}</tbody>
    </table></div></Panel>
  </div>;
}
