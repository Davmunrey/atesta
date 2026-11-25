"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { FilterBar, Pagination } from "@atesta/ui/lists";
import { Empty, LoadError, Loading, PageHeader, Panel } from "@atesta/ui/page-frame";
import { type ListQuery, PLANS, SORTS, STATES, listAddress, parseListQuery, useOrganizations } from "@/lib/api/organizations";
import { HealthBadge, PlanName, StateBadge } from "./organization-labels";

/** Screen 2 of the operator-portal spec: every organization, found by name or id, filtered,
 *  sorted and paged by 50; the address keeps the search, so a list can be shared and revisited. */
export function OrganizationList() {
  const t = useTranslations("organizations");
  const format = useFormatter();
  const router = useRouter();
  const query = parseListQuery(useSearchParams());
  const list = useOrganizations(query);
  const [text, setText] = useState(query.q);
  const go = (change: Partial<ListQuery>) => router.replace(listAddress({ ...query, page: 1, ...change }));
  const filtered = query.q !== "" || query.state !== "" || query.plan !== "" || query.health || query.billing;
  return <>
    <PageHeader title={t("title")} description={t("description")} />
    <Panel className="panel-flow">
      <FilterBar label={t("filters")}>
        <form role="search" onSubmit={(e) => { e.preventDefault(); go({ q: text.trim() }); }}>
          <label>{t("search")}<input type="search" className="field" value={text} onChange={(e) => setText(e.target.value)} maxLength={200} /></label>
          <button type="submit" className="dashboard-button">{t("searchAction")}</button>
        </form>
        <label>{t("state")}<select className="field" value={query.state} onChange={(e) => go({ state: e.target.value as ListQuery["state"] })}>
          <option value="">{t("all")}</option>{STATES.map((s) => <option key={s} value={s}>{t(`states.${s}`)}</option>)}</select></label>
        <label>{t("plan")}<select className="field" value={query.plan} onChange={(e) => go({ plan: e.target.value as ListQuery["plan"] })}>
          <option value="">{t("all")}</option>{PLANS.map((p) => <option key={p} value={p}>{t(`plans.${p}`)}</option>)}</select></label>
        <button type="button" className="dashboard-button" aria-pressed={query.health} onClick={() => go({ health: !query.health })}>{t("needsAttention")}</button>
        <button type="button" className="dashboard-button" aria-pressed={query.billing} onClick={() => go({ billing: !query.billing })}>{t("billingMissing")}</button>
        <label>{t("sort")}<select className="field" value={query.sort} onChange={(e) => go({ sort: e.target.value as ListQuery["sort"] })}>
          {SORTS.map((s) => <option key={s} value={s}>{t(`sorts.${s}`)}</option>)}</select></label>
      </FilterBar>
      {list.isPending ? <Loading />
        : list.isError ? <LoadError error={list.error} onRetry={() => void list.refetch()} />
        : list.data.rows.length === 0 ? <>
          <Empty>{filtered ? t("noMatch") : t("empty")}</Empty>
          {filtered ? <button type="button" className="dashboard-button" onClick={() => { setText(""); router.replace("/"); }}>{t("clear")}</button> : null}
        </>
        : <>
          <div className="table-region" role="region" aria-label={t("results")} tabIndex={0}><table className="w-full text-left">
            <thead><tr><th scope="col">{t("name")}</th><th scope="col">{t("state")}</th><th scope="col">{t("plan")}</th>
              <th scope="col">{t("members")}</th><th scope="col">{t("connections")}</th><th scope="col">{t("lastActivity")}</th></tr></thead>
            <tbody>{list.data.rows.map((row) => <tr key={row.id}>
              <td><Link href={`/organization?id=${row.id}`} className="text-link underline">{row.name}</Link></td>
              <td data-label={t("state")}><StateBadge state={row.state} /></td>
              <td data-label={t("plan")}><PlanName plan={row.plan} isDefault={row.plan_default} /></td>
              <td data-label={t("members")}>{format.number(row.members)}</td>
              <td data-label={t("connections")}><HealthBadge health={row.health} /></td>
              <td data-label={t("lastActivity")}>{row.last_activity ? format.dateTime(new Date(row.last_activity), { dateStyle: "medium" }) : t("never")}</td>
            </tr>)}</tbody>
          </table></div>
          <Pagination page={list.data.page} pageSize={list.data.page_size} total={list.data.total} onPage={(page) => go({ page })} />
        </>}
    </Panel>
  </>;
}
