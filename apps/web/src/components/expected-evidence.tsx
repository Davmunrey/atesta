"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import type { components } from "@/lib/api/schema";

type Evidence = components["schemas"]["ExpectedEvidence"];
export type GuideReference = Evidence["items"][number]["ref"];

/** Formats a guide reference: cited, never copied. */
export function useGuideReference() {
  const t = useTranslations("expectedEvidence");
  const format = useFormatter();
  return (ref: GuideReference) => t("reference", { guide: ref.guide, section: ref.section, page: ref.page,
    edition: format.dateTime(new Date(`${ref.edition}-01T00:00:00Z`), { month: "long", year: "numeric", timeZone: "UTC" }) });
}

/** What an auditor is likely to ask for: the pack's checklist, a candidate until the owner signs it,
 *  each item with its guide reference (requirement-register spec, issue 226). Atesta's own words; the guide is cited, not copied.
 *  A reference shared by every item is stated once. Variants: a disclosure in the console's measure
 *  sheet ("row"); the dossier's, opened only while printing ("print", ui-polish spec, issue 295); open
 *  in the public sample, which names the Atesta team, never a person ("sample", issue 426). */
export function ExpectedEvidence({ evidence, variant = "row" }: { evidence: Evidence; variant?: "row" | "print" | "sample" }) {
  const t = useTranslations("expectedEvidence");
  const format = useFormatter();
  const english = useLocale() === "en";
  const details = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const node = details.current;
    if (variant !== "print" || !node) return;
    let wasOpen = node.open;
    const before = () => { wasOpen = node.open; node.open = true; };
    const after = () => { node.open = wasOpen; };
    window.addEventListener("beforeprint", before);
    window.addEventListener("afterprint", after);
    return () => { window.removeEventListener("beforeprint", before); window.removeEventListener("afterprint", after); };
  }, [variant]);
  const reference = useGuideReference();
  const references = new Set(evidence.items.map((item) => reference(item.ref)));
  const shared = references.size === 1 ? [...references][0] : null;
  const title = t("title", { count: evidence.items.length });
  const content = <>
    <p className="text-sm text-muted">{variant === "sample" ? t("reviewedTeam") : evidence.reviewed_by && evidence.reviewed_on
      ? t("reviewed", { name: evidence.reviewed_by, date: format.dateTime(new Date(`${evidence.reviewed_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) })
      : t("candidate")}</p>
    {shared ? <p className="text-sm text-muted">{t("shared", { reference: shared })}</p> : null}
    <ul className="dossier-list">{evidence.items.map((item, i) => <li key={i}>{shared ? english ? item.en : item.es : <>
      <span className="block">{english ? item.en : item.es}</span>
      <span className="block text-sm text-muted">{reference(item.ref)}</span>
    </>}</li>)}</ul>
  </>;
  if (variant === "sample") return <div className="row-section expected-evidence"><p className="measure-sheet-section">{title}</p>{content}</div>;
  return <details ref={details} className={`${variant === "print" ? "catalog-disclosure" : "row-section"} expected-evidence`}>
    <summary>{title}</summary>{content}
  </details>;
}
