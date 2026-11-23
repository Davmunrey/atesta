"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useId, useState } from "react";
import type { components } from "@/lib/api/schema";

type Guide = components["schemas"]["ScopeGuideOut"];
type Asset = { id: number; name: string; type: "information" | "service"; values: Record<string, string> };
type TermLabel = (term: string) => { text: string; lang: string | undefined };

/** The highest level per dimension among the assets, and the category the highest one leads to.
 *  An empty value is N/A and counts for nothing (requirement-register spec, issue 225). */
export function valuation(guide: Guide, levels: string[], assets: Asset[]) {
  const highest = (values: string[]) => values.filter((v) => levels.includes(v)).sort((a, b) => levels.indexOf(b) - levels.indexOf(a))[0];
  const keys = [...new Set(guide.steps.map((s) => s.key))];
  const dimensions = Object.fromEntries(keys.flatMap((k) => {
    const level = highest(assets.map((a) => a.values[k] ?? ""));
    return level ? [[k, level]] : [];
  })) as Record<string, string>;
  const top = highest(Object.values(dimensions));
  return { dimensions, category: top ? guide.category_by_level[top] ?? null : null };
}

/** A worksheet that walks the pack's valuation steps, information first and then services. Nothing
 *  here is stored: "Use these levels" only fills the scope form, which the person then saves. */
export function ScopeGuide({ guide, levels, term, onApply }: {
  guide: Guide; levels: string[]; term: TermLabel; onApply: (dimensions: Record<string, string>, category: string | null) => void;
}) {
  const t = useTranslations("register.guide");
  const cite = useCite();
  const english = useLocale() === "en";
  const [assets, setAssets] = useState<Asset[]>([]);
  const [applied, setApplied] = useState(false);
  const add = (type: Asset["type"]) => { setApplied(false); setAssets([...assets, { id: Date.now() + assets.length, name: "", type, values: {} }]); };
  const update = (id: number, change: Partial<Asset>) => { setApplied(false); setAssets(assets.map((a) => (a.id === id ? { ...a, ...change } : a))); };
  const result = valuation(guide, levels, assets);
  const summary = Object.entries(result.dimensions).map(([k, v]) => `${term(k).text} ${term(v).text}`).join(" · ");
  return <details className="row-section scope-guide">
    <summary>{t("title")}</summary>
    <p className="text-sm text-muted">{guide.reviewed_by ? t("reviewed", { name: guide.reviewed_by }) : t("candidate")}</p>
    <ul className="dossier-list">{guide.notes.map((n, i) => <li key={i}>{english ? n.en : n.es} <span className="text-sm text-muted">({cite(n.ref)})</span></li>)}</ul>
    {assets.map((asset, index) => <AssetValuation key={asset.id} asset={asset} index={index} guide={guide} levels={levels} term={term}
      onChange={(change) => update(asset.id, change)} onRemove={() => setAssets(assets.filter((a) => a.id !== asset.id))} />)}
    <div className="form-actions">
      <button type="button" className="dashboard-button" onClick={() => add("information")}>{t("addInformation")}</button>
      <button type="button" className="dashboard-button" onClick={() => add("service")}>{t("addService")}</button>
    </div>
    <p role="status">{summary ? t("result", { levels: summary, category: result.category ? term(result.category).text : "—" }) : t("empty")}</p>
    <button type="button" className="dashboard-button" disabled={!summary}
      onClick={() => { onApply(result.dimensions, result.category); setApplied(true); }}>{t("apply")}</button>
    {applied ? <p className="text-sm text-muted">{t("applied")}</p> : null}
  </details>;
}

function AssetValuation({ asset, index, guide, levels, term, onChange, onRemove }: {
  asset: Asset; index: number; guide: Guide; levels: string[]; term: TermLabel; onChange: (change: Partial<Asset>) => void; onRemove: () => void;
}) {
  const t = useTranslations("register.guide");
  const cite = useCite();
  const english = useLocale() === "en";
  const id = useId();
  const label = asset.name.trim() || t(`unnamed.${asset.type}`, { number: index + 1 });
  return <fieldset className="scope-guide-asset">
    <legend>{label}</legend>
    <span className="axis-select"><label htmlFor={`${id}-name`}>{t(`name.${asset.type}`)}</label>
      <input id={`${id}-name`} maxLength={200} value={asset.name} onChange={(e) => onChange({ name: e.target.value })} /></span>
    {guide.steps.filter((s) => s.asset === asset.type).map((step) => <span key={step.key} className="axis-select">
      <label htmlFor={`${id}-${step.key}`}>{english ? step.en : step.es}</label>
      <select id={`${id}-${step.key}`} aria-describedby={`${id}-${step.key}-ref`} value={asset.values[step.key] ?? ""}
        onChange={(e) => onChange({ values: { ...asset.values, [step.key]: e.target.value } })}>
        <option value="">{t("notAssigned")}</option>
        {levels.map((l) => <option key={l} value={l} lang={term(l).lang}>{term(l).text}</option>)}
      </select>
      <span id={`${id}-${step.key}-ref`} className="text-sm text-muted">{cite(step.ref)}</span></span>)}
    <button type="button" className="dashboard-button" onClick={onRemove}>{t("remove", { name: label })}</button>
  </fieldset>;
}

function useCite() {
  const t = useTranslations("expectedEvidence");
  const format = useFormatter();
  return (ref: Guide["steps"][number]["ref"]) => t("reference", { guide: ref.guide, section: ref.section, page: ref.page,
    edition: format.dateTime(new Date(`${ref.edition}-01T00:00:00Z`), { month: "long", year: "numeric", timeZone: "UTC" }) });
}
