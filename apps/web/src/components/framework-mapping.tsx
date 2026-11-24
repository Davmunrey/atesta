"use client";

import { useLocale, useTranslations } from "next-intl";
import type { FrameworkMapping } from "@/lib/catalog/landing";

/**
 * One common control and the requirement it answers in each framework (DESIGN.md "Mapping table";
 * landing-legal A4), from signed mappings only. A console data table (`table-region`): it stacks
 * by its own width on a phone. Official references and titles stay in the source's language.
 */
export function FrameworkMappingTable({ mapping }: { mapping: FrameworkMapping }) {
  const t = useTranslations("landing.view.map");
  const english = useLocale() === "en";
  const control = english ? mapping.control.title_en : mapping.control.title_es;
  return <div className="table-region public-table" role="region" tabIndex={0} aria-label={t("caption", { control })}>
    <table>
      <caption>{t("caption", { control })}</caption>
      <thead><tr><th scope="col">{t("framework")}</th><th scope="col">{t("requirement")}</th></tr></thead>
      <tbody>{mapping.rows.map((row) => {
        const title = english && row.title_en ? row.title_en : row.title_es;
        return <tr key={row.framework}>
          <th scope="row">{t(`names.${row.framework}` as "names.ens_rd311_2022")}</th>
          <td data-label={t("requirement")}>
            <a href={row.source} className="text-link underline" lang="es">{row.reference}</a>
            <span className="block" lang={title === row.title_es ? "es" : "en"}>{title}</span>
          </td>
        </tr>;
      })}</tbody>
    </table>
    <p className="text-sm text-muted">{t("note")}</p>
  </div>;
}
