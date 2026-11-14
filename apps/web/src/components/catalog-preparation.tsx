"use client";

import { useLocale, useTranslations } from "next-intl";
import type { components } from "@/lib/api/schema";
import { CatalogReference } from "./catalog-reference";
import { ControlEvidence } from "./control-evidence";

type Context = components["schemas"]["PackContext"];
type Guidance = components["schemas"]["RequirementContext"];
type Control = components["schemas"]["PreparationControl"];

export function CatalogPreparation({ context, requirements, controls }: { context: Context; requirements: number; controls: number }) {
  const t = useTranslations("preparation");
  const english = useLocale() === "en";
  return <section className="catalog-preparation" aria-labelledby="preparation-title">
    <h2 id="preparation-title">{t(`states.${context.content_state}`)}</h2>
    <p>{english ? context.summary_en : context.summary_es}</p>
    <p className="catalog-boundary">{t("disabled")}</p>
    <nav className="preparation-jumps" aria-label={t("navigate")}>
      <a href="#requirements-heading">{t("requirementsCount", { count: requirements })}</a>
      {controls > 0 ? <a href="#preparation-controls-heading">{t("controlsCount", { count: controls })}</a> : null}
    </nav>
    <div className="catalog-context-grid">
      <details className="catalog-disclosure"><summary>{t("scope")}</summary>
        <p>{english ? context.scope_en : context.scope_es}</p>
        <h3>{t("applicability")}</h3><p>{english ? context.applicability_en : context.applicability_es}</p>
      </details>
      <details className="catalog-disclosure"><summary>{t("missing")}</summary><p>{english ? context.limitations_en : context.limitations_es}</p></details>
      <details className="catalog-disclosure"><summary>{t("sources")}</summary>
        <p>{t("verified", { date: context.verified_on })}</p>
        <ul>{context.source_refs.map((value) => <li key={value}><CatalogReference value={value} /></li>)}</ul>
      </details>
    </div>
  </section>;
}

export function RequirementGuidance({ guidance }: { guidance: Guidance }) {
  const t = useTranslations("preparation");
  return <div className="requirement-guidance">
    <h3>{t("selection")}</h3><p lang="es">{guidance.selection_basis}</p>
    <table className="selection-table"><caption>{t("selectionHelp")}</caption>
      <thead><tr><th scope="col">{t("level")}</th><th scope="col">{t("rule")}</th></tr></thead>
      <tbody>{guidance.selection_rules.map((row) => <tr key={row.level}><th scope="row" lang="es">{row.level}</th><td lang="es">{row.rule}</td></tr>)}</tbody>
    </table>
    <p className="official-text" lang="es">{guidance.applicability_es}</p>
    <details className="catalog-disclosure"><summary>{t("officialText")}</summary><p className="official-text" lang="es">{guidance.official_text_es}</p></details>
  </div>;
}

export function PreparationGuides({ orgId, controls }: { orgId: string; controls: Control[] }) {
  const t = useTranslations("preparation");
  const framework = useTranslations("framework");
  const english = useLocale() === "en";
  if (!controls.length) return null;
  return <section className="preparation-guides" aria-labelledby="preparation-controls-heading">
    <h2 id="preparation-controls-heading">{t("controls")}</h2><p>{t("controlsHelp")}</p>
    {controls.map((control) => <details className="catalog-disclosure preparation-control" key={control.key}>
      <summary><span>{english ? control.title_en : control.title_es}</span><span className="text-muted">{t(control.manual ? "manual" : "technical")}</span></summary>
      <p className="requirement-code">{control.key}</p>
      <p className="control-description">{english ? control.description_en : control.description_es}</p>
      {control.checks.length > 0 ? <div className="configuration-checks"><h3>{t("candidateChecks")}</h3><ul>{control.checks.map((check) => <li key={`${check.engine}:${check.check_id}`}><span className="requirement-code">{check.check_id}</span><span>{check.engine}</span></li>)}</ul></div> : null}
      <div className="control-references"><h3>{framework("applyGuide")}</h3><ul>{control.remediation_refs.map((value) => <li key={value}><CatalogReference value={value} /></li>)}</ul></div>
      <ControlEvidence orgId={orgId} controlKey={control.key} />
    </details>)}
  </section>;
}
