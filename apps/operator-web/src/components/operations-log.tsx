"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { FilterBar, Pagination } from "@atesta/ui/lists";
import { Empty, LoadError, Loading, Panel } from "@atesta/ui/page-frame";
import { ACTIONS, type EventFilters, useEvents, useStaffList } from "@/lib/api/admin";
import { AdminPage } from "./admin-page";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Screen 11 of the operator-portal spec: the operator trail, by organization, staff member and
 *  action, with each row's internal reason and metadata. */
export function OperationsLog() {
  const t = useTranslations("log");
  return <AdminPage title={t("title")} description={t("description")}><OperationsLogBody /></AdminPage>;
}

function OperationsLogBody() {
  const t = useTranslations("log");
  const format = useFormatter();
  const ids = { org: useId(), staff: useId(), action: useId() };
  const [filters, setFilters] = useState<EventFilters>({ org_id: "", staff_id: "", action: "", page: 1 });
  const [org, setOrg] = useState("");
  const staff = useStaffList();
  const events = useEvents(filters);
  const email = new Map((staff.data ?? []).map((s) => [s.id, s.email]));
  const set = (change: Partial<EventFilters>) => setFilters({ ...filters, page: 1, ...change });
  const badOrg = org.trim() !== "" && !UUID.test(org.trim());
  return <>
    <Panel className="panel-flow">
      <FilterBar label={t("filters")}>
        <form role="search" onSubmit={(e) => { e.preventDefault(); if (!badOrg) set({ org_id: org.trim() }); }}>
          <label htmlFor={ids.org}>{t("organization")}<input id={ids.org} className="field font-mono" value={org} onChange={(e) => setOrg(e.target.value)}
            aria-invalid={badOrg || undefined} placeholder={t("organizationHint")} /></label>
          <button type="submit" className="dashboard-button" disabled={badOrg}>{t("filter")}</button>
        </form>
        <label htmlFor={ids.staff}>{t("staff")}<select id={ids.staff} className="field" value={filters.staff_id} onChange={(e) => set({ staff_id: e.target.value })}>
          <option value="">{t("all")}</option>{(staff.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.email}</option>)}</select></label>
        <label htmlFor={ids.action}>{t("action")}<select id={ids.action} className="field" value={filters.action} onChange={(e) => set({ action: e.target.value })}>
          <option value="">{t("all")}</option>{ACTIONS.map((a) => <option key={a} value={a}>{t(`actions.${a.replace(".", "_")}`)}</option>)}</select></label>
      </FilterBar>
      {events.isPending ? <Loading />
        : events.isError ? <LoadError error={events.error} onRetry={() => void events.refetch()} />
        : events.data.rows.length === 0 ? <Empty>{t("empty")}</Empty>
        : <>
          <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="w-full text-left">
            <thead><tr><th scope="col">{t("when")}</th><th scope="col">{t("action")}</th><th scope="col">{t("staff")}</th>
              <th scope="col">{t("organization")}</th><th scope="col">{t("reason")}</th><th scope="col">{t("details")}</th></tr></thead>
            <tbody>{events.data.rows.map((e) => <tr key={e.id}>
              <td>{format.dateTime(new Date(e.occurred_at), { dateStyle: "medium", timeStyle: "short" })}</td>
              <td data-label={t("action")}>{(ACTIONS as readonly string[]).includes(e.action) ? t(`actions.${e.action.replace(".", "_")}`) : t("otherAction")}</td>
              <td data-label={t("staff")}>{e.staff_id ? email.get(e.staff_id) ?? t("formerStaff") : t("runner")}</td>
              <td data-label={t("organization")}>{e.organization_id ? <Link href={`/organization?id=${e.organization_id}`} className="text-link underline font-mono">{e.organization_id.slice(0, 8)}</Link> : "—"}</td>
              <td data-label={t("reason")}>{e.reason ?? "—"}</td>
              <td data-label={t("details")} className="font-mono">{Object.entries(e.metadata).map(([k, v]) => `${k}: ${String(v)}`).join(" · ") || "—"}</td>
            </tr>)}</tbody>
          </table></div>
          <Pagination page={events.data.page} pageSize={events.data.page_size} total={events.data.total} onPage={(page) => setFilters({ ...filters, page })} />
        </>}
    </Panel>
  
  </>;
}
