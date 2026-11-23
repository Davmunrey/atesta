"use client";

import { useTranslations } from "next-intl";
import { type KeyboardEvent, useId, useRef, useState } from "react";
import { DossierView, IncidentView, MeasureView, RecordsView } from "./moment-views";
import { OverviewView } from "./overview-view";

const TABS = [["overview", OverviewView], ["assess", MeasureView], ["routines", RecordsView], ["incident", IncidentView], ["dossier", DossierView]] as const;

/** The hero's product views as a real tablist (A3, issue 373): click or arrow keys, Home and End;
 *  it never advances on its own. Inactive panels are hidden, so only one view is read. */
export function HeroTabs() {
  const t = useTranslations("landing.tabs");
  const id = useId();
  const [active, setActive] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const go = (n: number) => { const next = (n + TABS.length) % TABS.length; setActive(next); tabs.current[next]?.focus(); };
  const onKey = (e: KeyboardEvent) => {
    const keys: Record<string, number> = { ArrowRight: active + 1, ArrowLeft: active - 1, Home: 0, End: TABS.length - 1 };
    if (e.key in keys) { e.preventDefault(); go(keys[e.key]!); }
  };
  return <div className="hero-tabs">
    <div role="tablist" aria-label={t("label")} className="hero-tablist" onKeyDown={onKey}>
      {TABS.map(([key], n) => <button key={key} type="button" role="tab" id={`${id}-tab-${n}`} aria-controls={`${id}-panel-${n}`}
        aria-selected={active === n} tabIndex={active === n ? 0 : -1} ref={(el) => { tabs.current[n] = el; }} onClick={() => setActive(n)}>{t(key)}</button>)}
    </div>
    {TABS.map(([key, View], n) => <div key={key} role="tabpanel" id={`${id}-panel-${n}`} aria-labelledby={`${id}-tab-${n}`} hidden={active !== n} className="hero-panel">
      <View />
    </div>)}
  </div>;
}
