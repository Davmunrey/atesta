"use client";

import { useTranslations } from "next-intl";
import type { ReactNode, Ref } from "react";
import { CatalogReference } from "./catalog-reference";
import { useGuideReference, type GuideReference } from "./expected-evidence";
import { Icon } from "@atesta/ui/icons";

/**
 * One measure, wherever the product shows it (DESIGN.md "Measure sheet"; console-unification
 * part 4). Two modes, one anatomy: the code and title with the state, then the record (the
 * organization's own assessment and the guide's expected evidence) beside the law (the official
 * text and its source), side by side from 48rem of the sheet's own width.
 * - sample (no `row`): an open, static article for public pages. It sits inside a product frame,
 *   so its section labels are not headings and the page outline stays whole.
 * - console (`row`): the register's disclosure row; `children` sit below both columns.
 */
export function MeasureSheet({ code, title, titleLang, state, record, law, source, row, ref, children }: {
  code: string; title: string; titleLang?: string; state: ReactNode; record: ReactNode; law: ReactNode; source?: string | null;
  row?: { id: string; open: boolean }; ref?: Ref<HTMLDetailsElement>; children?: ReactNode;
}) {
  const t = useTranslations("framework");
  const heading = <span className="requirement-heading"><span className="requirement-code">{code}</span><strong lang={titleLang}>{title}</strong></span>;
  const body = <div className="measure-sheet-body">
    <div className="measure-sheet-record">{record}</div>
    <div className="measure-sheet-law">{law}{source ? <p className="requirement-source">{t("source")}: <CatalogReference value={source} /></p> : null}</div>
  </div>;
  if (!row) return <article className="measure-sheet" aria-label={`${code} ${title}`}><div className="measure-sheet-head">{heading}{state}</div>{body}</article>;
  return <details ref={ref} id={row.id} className="measure-sheet requirement-row" open={row.open}>
    <summary>{heading}{state}
      <svg className="disclosure-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg>
    </summary>
    <div className="requirement-body">{body}{children}</div>
  </details>;
}

/** The official text as a ruled quotation, paragraph by paragraph, in its own language. */
export function OfficialText({ text, lang, highlightLast = false }: { text: string | string[]; lang: string; highlightLast?: boolean }) {
  const paragraphs = typeof text === "string" ? text.split("\n\n") : text;
  const last = paragraphs.length - 1;
  return <blockquote className="official-text" lang={lang}>{paragraphs.map((p, i) => <p key={i}>{highlightLast && i === last ? <mark className="hl">{p}</mark> : p}</p>)}</blockquote>;
}

// Never colour alone (ui-polish spec): each state carries its own drawn icon beside the label.
const STATE_ICON = { implemented: "done", partially_implemented: "partial", not_implemented: "missing", not_applicable: "notApplicable", pending: "pending" } as const;
type Implementation = "implemented" | "partially_implemented" | "not_implemented";
type Decision = "applies" | "not_applicable" | "undecided";

/** The self-assessment state; a pending measure adds the proposal as a hint. */
export function AssessmentState({ state, hint }: { state: keyof typeof STATE_ICON; hint?: Decision }) {
  const t = useTranslations("register");
  return <span className="requirement-state" data-assessment={state}><Icon name={STATE_ICON[state]} size={16} />{t(`states.${state}`)}
    {hint && hint !== "undecided" ? <span className="proposal-hint"> · {t(`proposal.${hint}`)}</span> : null}</span>;
}

/** "Tu autoevaluación", then the proposal from the official tables (or a cited profile). A heading
 *  in the console; a label in the sample, whose frame keeps the page outline. */
export function AssessmentIntro({ proposal, heading = true }: {
  proposal: { decision: Decision; rule?: string | null; level?: string | null; source?: GuideReference | null; criterion?: GuideReference | null }; heading?: boolean;
}) {
  const t = useTranslations("register");
  const cite = useGuideReference();
  const Label = heading ? "h3" : "p";
  const official = (chunks: ReactNode) => <span lang="es">{chunks}</span>;
  const { decision, rule, level, source, criterion } = proposal;
  return <>
    <Label className="measure-sheet-section">{t("yourAssessment")}</Label>
    <p className="text-sm text-muted">{decision === "undecided" ? t("proposalUndecided")
      : source ? t.rich("proposalProfile", { decision: t(`proposal.${decision}`), rule: rule ?? "", reference: cite(source), official })
      : t.rich("proposalText", { decision: t(`proposal.${decision}`), rule: rule ?? "", level: level ?? "", official })}
      {criterion ? <> {t("proposalCriterion", { reference: cite(criterion) })}</> : null}</p>
  </>;
}

/** The recorded fields of an assessment (or of an agent's proposal), in one order everywhere. */
export function AssessmentFields({ value, owner, dated, children }: {
  value: { applicability: "applies" | "not_applicable"; implementation: Implementation; regularly_reviewed?: boolean; performed_by?: string; justification?: string; notes?: string };
  owner?: string; dated?: string; children?: ReactNode;
}) {
  const t = useTranslations("register");
  const row = (label: string, text: ReactNode) => <div><dt>{label}</dt><dd>{text}</dd></div>;
  return <dl className="assessment-summary">
    {owner ? row(t("owner"), owner) : null}
    {row(t("applicability"), t(`proposal.${value.applicability}`))}
    {value.applicability === "applies" ? row(t("implementation"), `${t(`states.${value.implementation}`)}${value.regularly_reviewed ? ` · ${t("regularlyReviewed")}` : ""}`) : null}
    {value.performed_by ? row(t("performedBy"), `${value.performed_by}${dated ? ` · ${dated}` : ""}`) : null}
    {value.justification ? row(t("justification"), value.justification) : null}
    {value.notes ? row(t("notes"), value.notes) : null}
    {children}
  </dl>;
}
