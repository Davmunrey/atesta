"use client";

import { useTranslations } from "next-intl";
import { type ComponentType, useEffect, useRef, useState } from "react";
import { DossierView, IncidentView, RecordsView } from "./moment-views";
import { OverviewView } from "./overview-view";
import { SampleLabelled } from "./view-frame";

/** From assessing to the dossier; connecting comes last because it has not shipped (A4, issue 221). */
const STEPS = ["assess", "routines", "incidents", "dossier", "connect"] as const;
type Step = (typeof STEPS)[number];
/** Connect has no product view, only its "Próximamente" tag. */
const VIEWS: Partial<Record<Step, ComponentType>> = { assess: OverviewView, routines: RecordsView, incidents: IncidentView, dossier: DossierView };

/**
 * "Cómo funciona" (amendment A2, refined by A4). On wide screens with motion allowed, the steps
 * scroll beside one sticky frame whose stage follows the step in view (IntersectionObserver; no
 * scroll-jacking). The sticky frame is decorative for assistive technology: each step carries its
 * meaning, and on phones or with reduced motion each step shows its own frame on its own row. The
 * section says "Datos de ejemplo" once, so its frames do not repeat it.
 */
export function PinnedSteps() {
  const t = useTranslations("landing");
  const [active, setActive] = useState(1);
  const items = useRef<(HTMLLIElement | null)[]>([]);
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.step));
    }, { rootMargin: "-45% 0px -45% 0px" });
    for (const item of items.current) if (item) observer.observe(item);
    return () => observer.disconnect();
  }, []);
  return <section className="landing-ink landing-pinned" data-stage={active} aria-labelledby="how-title">
    <SampleLabelled.Provider value>
      <div className="landing-ink-inner landing-pinned-grid">
        <div className="landing-pinned-text">
          <div className="landing-pinned-head">
            <h2 id="how-title" className="landing-h2">{t("how.title")}</h2>
            <p className="landing-soon landing-sample">{t("sample")}</p>
          </div>
          <ol className="landing-steps">{STEPS.map((key, i) => {
            const View = VIEWS[key];
            return <li key={key} data-key={key} data-step={i + 1} ref={(el) => { items.current[i] = el; }}>
              <div className="landing-step-copy">
                <span className="landing-step-number" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
                <p className="landing-step-title">{t(`how.steps.${key}.title`)}{View ? null : <span className="landing-soon">{t("soon")}</span>}</p>
                <p className="landing-step-body">{t(`how.steps.${key}.body`)}</p>
              </div>
              {View ? <div className="landing-step-stage"><View /></div> : null}
            </li>;
          })}</ol>
        </div>
        <div className="landing-stage-frame" aria-hidden="true">
          <div className="landing-stage-layers">{STEPS.map((key, i) => {
            const View = VIEWS[key];
            return View ? <div key={key} data-stage-view={key} className="landing-stage" data-active={active === i + 1}><View /></div> : null;
          })}</div>
        </div>
      </div>
    </SampleLabelled.Provider>
  </section>;
}
