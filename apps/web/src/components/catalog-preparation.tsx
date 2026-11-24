"use client";

import { useLocale, useTranslations } from "next-intl";
import type { components } from "@/lib/api/schema";
import { CatalogReference } from "./catalog-reference";
import { ControlEvidence } from "./control-evidence";
import { OfficialText } from "./measure-sheet";

type Context = components["schemas"]["PackContext"];
type Guidance = components["schemas"]["RequirementContext"];
type Control = components["schemas"]["PreparationControl"];
type Coverage = components["schemas"]["Coverage"];

export function CatalogPreparation({ context, requirements, controls, coverage = null }: { context: Context; requirements: number; controls: number; coverage?: Coverage | null }) {
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
      {coverage ? <SourceCoverage coverage={coverage} /> : null}
    </div>
  </section>;
}

/** Official text of a requirement; English only when the act itself is official in English. */
export function RequirementGuidance({ guidance }: { guidance: Guidance }) {
  const t = useTranslations("preparation");
  const english = useLocale() === "en";
  const rules = guidance.selection_rules ?? [];
  const ownLanguage = english ? guidance.official_text_en : guidance.official_text_es;
  return <div className="requirement-guidance">
    {guidance.selection_basis && rules.length ? <>
      <h3>{t("selection")}</h3><p lang="es">{guidance.selection_basis}</p>
      <table className="selection-table"><caption>{t("selectionHelp")}</caption>
        <thead><tr><th scope="col">{t("level")}</th><th scope="col">{t("rule")}</th></tr></thead>
        <tbody>{rules.map((row) => <tr key={row.level}><th scope="row" lang="es">{row.level}</th><td lang="es">{row.rule}</td></tr>)}</tbody>
      </table>
    </> : null}
    {guidance.applicability_es ? <p className="official-text" lang="es">{guidance.applicability_es}</p> : null}
    <details className="catalog-disclosure">
      {ownLanguage ? <><summary>{t("officialTextOwn")}</summary><OfficialText text={ownLanguage} lang={english ? "en" : "es"} /></>
        : <><summary>{t("officialText")}</summary><OfficialText text={guidance.official_text_es} lang="es" /></>}
    </details>
  </div>;
}

/** Every unit of the official source, imported as requirements or excluded with its reason. */
export function SourceCoverage({ coverage }: { coverage: Coverage }) {
  const t = useTranslations("coverage");
  const english = useLocale() === "en";
  const count = (status: "covered" | "excluded") =>
    coverage.entries.filter((e) => e.status === status).reduce((n, e) => n + e.units.length, 0);
  const unit = (id: string) => {
    const [, kind = "", number = ""] = /^([a-z]+)(.*)$/.exec(id) ?? [];
    if (kind === "art") return t("units.art", { n: number });
    if (kind === "annex") return t("units.annex", { n: roman(Number(number)) });
    if (kind === "da" || kind === "df") return t(`units.${kind}`, { n: number });
    if (kind === "dt" || kind === "dd") return t(`units.${kind}`);
    return id;
  };
  return <details className="catalog-disclosure source-coverage"><summary>{t("title")}</summary>
    <p>{t("summary", { covered: count("covered"), excluded: count("excluded") })}</p>
    <p className="text-sm text-muted">{t("help")}</p>
    <ul className="coverage-list">{coverage.entries.map((entry) => <li key={entry.units.join(",")}>
      <strong>{entry.units.map(unit).join(", ")}</strong>
      {" · "}<span>{entry.status === "covered"
        ? t("covered", { count: entry.requirements?.length ?? 0 })
        : english ? entry.reason_en : entry.reason_es}</span>
    </li>)}</ul>
  </details>;
}

function roman(value: number): string {
  const numerals: [number, string][] = [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
  let rest = value;
  let out = "";
  for (const [n, symbol] of numerals) while (rest >= n) { out += symbol; rest -= n; }
  return out || String(value);
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
