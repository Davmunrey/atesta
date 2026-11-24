"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import type { HeroMeasure } from "@/lib/catalog/landing";
import { CatalogReference } from "./catalog-reference";
import { Icon } from "./icons";

type Implementation = "implemented" | "partially_implemented" | "not_implemented";
const STATE_ICON = { implemented: "done", partially_implemented: "partial", not_implemented: "missing" } as const;
export type SheetAssessment = { implementation: Implementation; owner: string; notes: string };

/**
 * One measure as the console's requirement row shows it (DESIGN.md "Measure sheet"; landing-legal
 * A4): code and title with the assessment state, "Tu autoevaluación" with the proposal from the
 * official tables, the guide's expected evidence, then the official text and its source. Same
 * classes and message keys as framework-detail.tsx, so a public page and the console read alike.
 * Public pages name the Atesta team, never a reviewer. The excerpt's last paragraph is highlighted.
 * It sits inside a product frame, so its section labels are not headings: the page outline stays whole.
 */
export function MeasureSheet({ measure, assessment }: { measure: HeroMeasure; assessment: SheetAssessment }) {
  const t = useTranslations("register");
  const evidence = useTranslations("expectedEvidence");
  const source = useTranslations("framework");
  const sheet = useTranslations("landing.view.hero");
  const format = useFormatter();
  const english = useLocale() === "en";
  const edition = (value: string) => format.dateTime(new Date(`${value}-01T00:00:00Z`), { month: "long", year: "numeric", timeZone: "UTC" });
  const refs = new Set(measure.evidence.map(({ ref }) => evidence("reference", { ...ref, edition: edition(ref.edition) })));
  const last = measure.paragraphs.length - 1;
  return <article className="measure-sheet" aria-label={`${measure.code} ${measure.title}`}>
    <div className="measure-sheet-head">
      <span className="requirement-heading"><span className="requirement-code">{measure.code}</span><strong lang="es">{measure.title}</strong></span>
      <span className="requirement-state" data-assessment={assessment.implementation}><Icon name={STATE_ICON[assessment.implementation]} size={16} />{t(`states.${assessment.implementation}`)}</span>
    </div>
    <div className="measure-sheet-body">
      <div className="measure-sheet-record">
        <div className="assessment-card">
          <p className="measure-sheet-section">{t("yourAssessment")}</p>
          <p className="text-sm text-muted">{t.rich("proposalText", { decision: t("proposal.applies"), level: measure.level, rule: measure.rule, official: (chunks) => <span lang="es">{chunks}</span> })}</p>
          <dl className="assessment-summary">
            <div><dt>{t("owner")}</dt><dd>{assessment.owner}</dd></div>
            <div><dt>{t("applicability")}</dt><dd>{t("proposal.applies")}</dd></div>
            <div><dt>{t("implementation")}</dt><dd>{t(`states.${assessment.implementation}`)}</dd></div>
            <div><dt>{t("notes")}</dt><dd>{assessment.notes}</dd></div>
          </dl>
        </div>
        <div className="row-section expected-evidence">
          <p className="measure-sheet-section">{evidence("title", { count: measure.evidence.length })}</p>
          <p className="text-sm text-muted">{evidence("reviewedTeam")}</p>
          {refs.size === 1 ? <p className="text-sm text-muted">{evidence("shared", { reference: [...refs][0]! })}</p> : null}
          <ul className="dossier-list">{measure.evidence.map((item) => <li key={item.es}>{english ? item.en : item.es}</li>)}</ul>
        </div>
      </div>
      <div className="measure-sheet-law">
        <p className="measure-sheet-section">{sheet("excerpt")}</p>
        <blockquote className="official-text" lang="es">{measure.paragraphs.map((p, i) => <p key={i}>{i === last ? <mark className="hl">{p}</mark> : p}</p>)}</blockquote>
        <p className="requirement-source">{source("source")}: <CatalogReference value={measure.source} /></p>
      </div>
    </div>
  </article>;
}
