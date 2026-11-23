"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import type { components } from "@/lib/api/schema";

type Evidence = components["schemas"]["ExpectedEvidence"];

/** What an auditor is likely to ask for: the pack's checklist, a candidate until the owner signs it,
 *  each item with its guide reference (requirement-register spec, issue 226). Atesta's own words; the guide is cited, not copied. */
export function ExpectedEvidence({ evidence, open = false }: { evidence: Evidence; open?: boolean }) {
  const t = useTranslations("expectedEvidence");
  const format = useFormatter();
  const english = useLocale() === "en";
  const edition = (value: string) => format.dateTime(new Date(`${value}-01T00:00:00Z`), { month: "long", year: "numeric", timeZone: "UTC" });
  return <details className="catalog-disclosure expected-evidence" open={open}>
    <summary>{t("title", { count: evidence.items.length })}</summary>
    <p className="text-sm text-muted">{evidence.reviewed_by && evidence.reviewed_on
      ? t("reviewed", { name: evidence.reviewed_by, date: format.dateTime(new Date(`${evidence.reviewed_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) })
      : t("candidate")}</p>
    <ul className="dossier-list">{evidence.items.map((item, i) => <li key={i}>
      <span className="block">{english ? item.en : item.es}</span>
      <span className="block text-sm text-muted">{t("reference", { guide: item.ref.guide, edition: edition(item.ref.edition), section: item.ref.section, page: item.ref.page })}</span>
    </li>)}</ul>
  </details>;
}
