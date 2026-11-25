"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";
import { Pagination } from "@atesta/ui/lists";
import { Empty, LoadError, Loading, Panel } from "@atesta/ui/page-frame";
import { useReceipts } from "@/lib/api/admin";
import { AdminPage } from "./admin-page";

/** Screen 9 of the operator-portal spec: erasure receipts. No names: erasure removed them. */
export function ErasedOrganizations() {
  const t = useTranslations("erased");
  return <AdminPage title={t("title")} description={t("description")}><ErasedOrganizationsBody /></AdminPage>;
}

function ErasedOrganizationsBody() {
  const t = useTranslations("erased");
  const format = useFormatter();
  const [page, setPage] = useState(1);
  const receipts = useReceipts(page);
  const day = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium" });
  return <>
    <Panel className="panel-flow">{receipts.isPending ? <Loading />
      : receipts.isError ? <LoadError error={receipts.error} onRetry={() => void receipts.refetch()} />
      : receipts.data.rows.length === 0 ? <Empty>{t("empty")}</Empty>
      : <>
        <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("organization")}</th><th scope="col">{t("requested")}</th><th scope="col">{t("erasedAt")}</th><th scope="col">{t("rows")}</th></tr></thead>
          <tbody>{receipts.data.rows.map((r) => <tr key={r.id}>
            <td className="font-mono">{r.organization_id}</td>
            <td data-label={t("requested")}>{day(r.closure_requested_at)}</td>
            <td data-label={t("erasedAt")}>{day(r.erased_at)}</td>
            <td data-label={t("rows")}>{format.number(r.rows)}</td>
          </tr>)}</tbody>
        </table></div>
        <Pagination page={receipts.data.page} pageSize={receipts.data.page_size} total={receipts.data.total} onPage={setPage} />
      </>}
    </Panel>
  
  </>;
}
