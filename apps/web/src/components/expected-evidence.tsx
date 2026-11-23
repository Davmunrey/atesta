"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import type { components } from "@/lib/api/schema";

type Evidence = components["schemas"]["ExpectedEvidence"];
type Ref = Evidence["items"][number]["ref"];

/** What an auditor is likely to ask for: the pack's checklist, a candidate until the owner signs it,
 *  each item with its guide reference (requirement-register spec, issue 226). Atesta's own words; the guide is cited, not copied.
 *  A reference shared by every item is stated once; the dossier opens the list only while printing (ui-polish spec, issue 295). */
export function ExpectedEvidence({ evidence, forPrint = false }: { evidence: Evidence; forPrint?: boolean }) {
  const t = useTranslations("expectedEvidence");
  const format = useFormatter();
  const english = useLocale() === "en";
  const details = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const node = details.current;
    if (!forPrint || !node) return;
    let wasOpen = node.open;
    const before = () => { wasOpen = node.open; node.open = true; };
    const after = () => { node.open = wasOpen; };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => { window.removeEventListener("beforeprint", before); window.removeEventListener("afterprint", after); };
  }, [forPrint]);
  const edition = (value: string) => format.dateTime(new Date(`${value}-01T00:00:00Z`), { month: "long", year: "numeric", timeZone: "UTC" });
  const reference = (ref: Ref) => t("reference", { guide: ref.guide, edition: edition(ref.edition), section: ref.section, page: ref.page });
  const references = new Set(evidence.items.map((item) => reference(item.ref)));
  const shared = references.size === 1 ? [...references][0] : null;
  return <details ref={details} className={`${forPrint ? "catalog-disclosure" : "row-section"} expected-evidence`}>
    <summary>{t("title", { count: evidence.items.length })}</summary>
    <p className="text-sm text-muted">{evidence.reviewed_by && evidence.reviewed_on
      ? t("reviewed", { name: evidence.reviewed_by, date: format.dateTime(new Date(`${evidence.reviewed_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) })
      : t("candidate")}</p>
    {shared ? <p className="text-sm text-muted">{t("shared", { reference: shared })}</p> : null}
    <ul className="dossier-list">{evidence.items.map((item, i) => <li key={i}>
      <span className="block">{english ? item.en : item.es}</span>
      {shared ? null : <span className="block text-sm text-muted">{reference(item.ref)}</span>}
    </li>)}</ul>
  </details>;
}
