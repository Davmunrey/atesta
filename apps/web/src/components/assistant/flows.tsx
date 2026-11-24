"use client";

import { useLocale, useTranslations } from "next-intl";
import { type ReactNode, useId, useState } from "react";
import { categoryFor, pick } from "@/lib/assistant/flows";
import type { Locale } from "@atesta/ui/i18n/locale";
import type { Doc, Index, Text } from "@/lib/assistant/types";
import { AnswerCard, Cites, Quote } from "./card";

export const FLOWS = ["category", "evidence", "profile", "clocks", "faq"] as const;
export type FlowKey = (typeof FLOWS)[number];
type Props = { index: Index; orgId?: string | null; announce: (message: string) => void };

/** A native radio group with a legend; the legend may hold a quote and its citation. */
function Choice({ legend, options, value, onChange }: { legend: ReactNode; options: { value: string; label: ReactNode }[]; value: string | undefined; onChange: (value: string) => void }) {
  const name = useId();
  return (
    <fieldset role="radiogroup" className="assistant-choice">
      <legend>{legend}</legend>
      <div className="assistant-options">
        {options.map((option) => <label key={option.value}><input type="radio" name={name} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} /> {option.label}</label>)}
      </div>
    </fieldset>
  );
}

const shown = (text: Text, locale: Locale) => { const p = pick(text, locale); return p ? <span lang={p.lang}>{p.value}</span> : null; };

export function CategoryFlow({ index, announce }: Props) {
  const t = useTranslations("assistant.flows.category");
  const locale = useLocale() as Locale;
  const [picked, setPicked] = useState<Record<string, string>>({});
  const flow = index.flows.valuation;
  if (!flow) return null;
  const category = categoryFor(flow, picked);
  const label = (term: string) => (flow.labels[term] ? shown(flow.labels[term], locale) : term);
  const choose = (key: string, level: string) => {
    const next = { ...picked, [key]: level };
    setPicked(next);
    const result = categoryFor(flow, next);
    if (result) announce(t("result", { category: pick(flow.labels[result] ?? { es: result, en: null }, locale)?.value ?? result }));
  };
  return (
    <>
      <p>{t("intro")}</p>
      {flow.steps.map((step) => <Choice key={step.key} value={picked[step.key]} onChange={(level) => choose(step.key, level)}
        legend={<><Quote text={step.question} as="span" /><Cites cites={[{ kind: "guide", ...step.cite }]} /></>}
        options={Object.keys(flow.categoryByLevel).map((level) => ({ value: level, label: label(level) }))} />)}
      {category ? (
        <section className="assistant-result" aria-label={t("title")}>
          <p className="assistant-result-title">{t("result", { category: pick(flow.labels[category] ?? { es: category, en: null }, locale)?.value ?? category })}</p>
          <p className="text-muted">{t("basis")}</p>
          <ul className="assistant-notes">{flow.notes.map((note, n) => <li key={n}><Quote text={note.text} as="span" /><Cites cites={[note.cite]} /></li>)}</ul>
        </section>
      ) : <p className="text-muted">{t("waiting")}</p>}
    </>
  );
}

function EvidenceFlow({ index, orgId }: Props) {
  const t = useTranslations("assistant.flows.evidence");
  const locale = useLocale() as Locale;
  const [code, setCode] = useState("");
  const id = useId();
  const doc = index.docs.find((d) => d.kind === "evidence" && d.code === code);
  return (
    <>
      <label htmlFor={id} className="assistant-label">{t("pick")}</label>
      <select id={id} className="assistant-field" value={code} onChange={(event) => setCode(event.target.value)}>
        <option value="">{t("choose")}</option>
        {index.flows.measures.map((m) => <option key={m.code} value={m.code}>{m.code} · {pick(m.title, locale)?.value}</option>)}
      </select>
      {doc ? <AnswerCard doc={doc} orgId={orgId} /> : null}
    </>
  );
}

function ProfileFlow({ index, orgId }: Props) {
  const t = useTranslations("assistant.flows.profile");
  const [low, setLow] = useState<string>();
  const [key, setKey] = useState<string>();
  const flow = index.flows.profiles;
  if (!flow) return null;
  const first = flow.profiles[0];
  const basis = first?.refs.find((ref) => ref.section === "2") ?? first?.refs[0];
  const profile = flow.profiles.find((p) => p.key === key);
  const doc = profile ? index.docs.find((d) => d.id === `${flow.framework}:890C:${profile.key}`) : undefined;
  return (
    <>
      <Choice legend={t("low")} value={low} onChange={setLow} options={[{ value: "yes", label: t("yes") }, { value: "no", label: t("no") }]} />
      {low === "no" && basis ? <div className="assistant-result"><p>{t("notFit")}</p><Cites cites={[{ kind: "guide", ...basis }]} /></div> : null}
      {low === "yes" ? <Choice legend={t("scope")} value={key} onChange={setKey} options={flow.profiles.map((p) => ({ value: p.key, label: p.key.includes("_ot") ? t("ot") : t("it") }))} /> : null}
      {low === "yes" && profile && doc ? (
        <>
          <AnswerCard doc={doc} orgId={orgId} />
          <details className="assistant-more">
            <summary>{t("levels")}</summary>
            <table className="assistant-table">
              <thead><tr><th scope="col">{t("measure")}</th><th scope="col">{t("value")}</th></tr></thead>
              <tbody>{Object.entries(profile.levels).map(([code, level]) => <tr key={code}>
                <th scope="row" className="font-mono">{code}</th>
                <td>{level}{profile.criteria[code] ? <span className="text-muted"> · {t("criterion", profile.criteria[code])}</span> : null}</td>
              </tr>)}</tbody>
            </table>
          </details>
        </>
      ) : null}
    </>
  );
}

function ClocksFlow({ index, orgId }: Props) {
  const t = useTranslations("assistant.flows.clocks");
  const locale = useLocale() as Locale;
  const [chosen, setChosen] = useState<string>();
  const sets = index.flows.clocks;
  const set = sets.find((s) => `${s.framework}:${s.needs}` === chosen);
  const doc = (id: string): Doc | undefined => index.docs.find((d) => d.id === id);
  return (
    <>
      <Choice legend={t("pick")} value={chosen} onChange={setChosen}
        options={sets.map((s) => ({ value: `${s.framework}:${s.needs}`, label: t(`needs.${s.needs}`, { framework: s.frameworkName }) }))} />
      {set ? (
        <section className="assistant-result" aria-label={t("title")}>
          <ol className="assistant-clocks">{set.clocks.map((clock) => {
            const after = set.clocks.find((c) => c.key === clock.after);
            const card = doc(`${set.framework}:clock:${clock.key}`);
            return <li key={clock.key}>
              <p className="assistant-clock-time">{clock.hours !== null ? t("hours", { count: clock.hours }) : t("months", { count: clock.months ?? 0 })}</p>
              {after ? <p className="text-muted">{t("after", { step: pick(after.title, locale)?.value ?? after.key })}</p> : null}
              {card ? <AnswerCard doc={card} orgId={orgId} /> : null}
            </li>;
          })}</ol>
          <h3 className="assistant-subtitle">{t("criteria")}</h3>
          {set.criteria.map((code) => { const card = doc(`${set.framework}:${code}`); return card ? <AnswerCard key={code} doc={card} orgId={orgId} /> : null; })}
        </section>
      ) : null}
    </>
  );
}

function FaqFlow({ index }: Props) {
  return <>{index.docs.filter((d) => d.kind === "faq").map((d) => <AnswerCard key={d.id} doc={d} />)}</>;
}

const VIEWS: Record<FlowKey, (props: Props) => ReactNode> = { category: CategoryFlow, evidence: EvidenceFlow, profile: ProfileFlow, clocks: ClocksFlow, faq: FaqFlow };

export function Flow({ flow, ...props }: Props & { flow: FlowKey }) {
  const View = VIEWS[flow];
  return <View {...props} />;
}
