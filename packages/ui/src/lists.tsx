"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

/** A list's filters above it (DESIGN.md, "Lists"): labelled fields and pressed toggles in one
 *  wrapping row; a toggle on shows the highlighter pair. */
export function FilterBar({ label, children }: { label: string; children: ReactNode }) {
  return <div role="group" aria-label={label} className="filters">{children}</div>;
}

/** Pages of a long list: where this page sits in the total, then previous and next. */
export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (page: number) => void }) {
  const t = useTranslations("pagination");
  const last = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize && page === 1) return null;
  return <nav aria-label={t("label")} className="pagination">
    <p role="status">{t("range", { from: Math.min((page - 1) * pageSize + 1, total), to: Math.min(page * pageSize, total), total })}</p>
    <div className="page-actions">
      <button type="button" className="dashboard-button" disabled={page <= 1} onClick={() => onPage(page - 1)}>{t("previous")}</button>
      <button type="button" className="dashboard-button" disabled={page >= last} onClick={() => onPage(page + 1)}>{t("next")}</button>
    </div>
  </nav>;
}
