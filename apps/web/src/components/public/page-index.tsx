"use client";

import { useTranslations } from "next-intl";

/** "On this page": jump links beside a subpage's headline (A3, issue 377). */
export function PageIndex({ items }: { items: { id: string; label: string }[] }) {
  const t = useTranslations("public");
  return <nav className="page-index" aria-label={t("onThisPage")}>
    <p className="page-index-label" aria-hidden="true">{t("onThisPage")}</p>
    <ol>{items.map((item) => <li key={item.id}><a href={`#${item.id}`}>{item.label}</a></li>)}</ol>
  </nav>;
}
