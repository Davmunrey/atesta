"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import synonyms from "@/content/assistant-synonyms.json";
import { legalEntity } from "@/content/legal-entity";
import { loadIndex } from "@/lib/assistant/flows";
import { synonymTable } from "@/lib/assistant/normalize";
import { type Hit, createEngine, search } from "@/lib/assistant/search";
import type { Index } from "@/lib/assistant/types";
import { AnswerCard } from "./card";
import { FLOWS, Flow, type FlowKey } from "./flows";

export type Surface = "landing" | "app";
type Props = { surface: Surface; orgId?: string | null; focusTick: number };
type State = { kind: "loading" } | { kind: "error" } | { kind: "ready"; index: Index };

/**
 * The assistant's content (assistant spec), loaded on first open: search over the static index,
 * cited answer cards, a plain "no answer" with the contact address, and the guided flows.
 * One status region announces results; the cards themselves are not live.
 */
export default function AssistantPanel({ surface, orgId, focusTick }: Props) {
  const t = useTranslations("assistant");
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [view, setView] = useState<FlowKey | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [status, setStatus] = useState("");
  const first = useRef<HTMLInputElement & HTMLButtonElement>(null);
  const field = useId();

  useEffect(() => {
    let live = true;
    loadIndex().then((index) => live && setState({ kind: "ready", index }), () => live && setState({ kind: "error" }));
    return () => { live = false; };
  }, [attempt]);

  const engine = useMemo(() => (state.kind === "ready" ? createEngine(state.index.docs, synonymTable(synonyms)) : null), [state]);
  useEffect(() => { first.current?.focus(); }, [focusTick, view, engine]);

  const announce = useCallback((message: string) => setStatus(message), []);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!engine || !query.trim()) return;
    const found = search(engine, query);
    setHits(found);
    setStatus(found.length > 0 ? t("results", { count: found.length }) : t("noAnswer"));
  };
  const open = (flow: FlowKey | null) => { setView(flow); setStatus(""); };
  const org = surface === "app" ? orgId : null;

  return (
    <div className="assistant-body">
      <p className="text-muted">{t("intro")}</p>
      {state.kind === "loading" ? <p className="text-muted">{t("loading")}</p> : null}
      {state.kind === "error" ? <div className="assistant-result"><p role="alert">{t("loadError")}</p><button type="button" className="assistant-button" onClick={() => { setState({ kind: "loading" }); setAttempt((n) => n + 1); }}>{t("retry")}</button></div> : null}
      {state.kind === "ready" && view === null ? (
        <>
          <form role="search" className="assistant-search" onSubmit={submit}>
            <label htmlFor={field} className="assistant-label">{t("search.label")}</label>
            <div className="assistant-search-row">
              <input ref={first} id={field} type="search" className="assistant-field" value={query} placeholder={t("search.placeholder")} onChange={(event) => setQuery(event.target.value)} autoComplete="off" />
              <button type="submit" className="assistant-button assistant-button-primary">{t("search.submit")}</button>
            </div>
          </form>
        </>
      ) : null}
      <p role="status" className="assistant-status">{status}</p>
      {state.kind === "ready" && view === null ? (
        <>
          {hits && hits.length > 0 ? <div className="assistant-cards">{hits.map((hit, n) => <AnswerCard key={hit.doc.id} doc={hit.doc} orgId={org} open={n === 0} />)}</div> : null}
          {hits && hits.length === 0 ? <p>{t.rich("contact", { email: legalEntity.email, link: (chunks) => <a href={`mailto:${legalEntity.email}`} className="text-link underline">{chunks}</a> })}</p> : null}
          <nav aria-labelledby={`${field}-flows`} className="assistant-flows">
            <h3 id={`${field}-flows`} className="assistant-subtitle">{t("flowsTitle")}</h3>
            <ul>{FLOWS.map((flow) => <li key={flow}><button type="button" className="assistant-flow" onClick={() => open(flow)}>{t(`flows.${flow}.title`)}</button></li>)}</ul>
          </nav>
        </>
      ) : null}
      {state.kind === "ready" && view !== null ? (
        <section aria-labelledby={`${field}-flow`} className="assistant-flow-view">
          <button ref={first} type="button" className="assistant-button" onClick={() => open(null)}>{t("back")}</button>
          <h3 id={`${field}-flow`} className="assistant-subtitle">{t(`flows.${view}.title`)}</h3>
          <Flow flow={view} index={state.index} orgId={org} announce={announce} />
        </section>
      ) : null}
    </div>
  );
}

export { AssistantPanel };
