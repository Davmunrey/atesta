"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { DossierView, MeasureView, RecordsView } from "./moment-views";
import { ViewFrame } from "./view-frame";

const STEPS = ["connect", "assess", "routines", "dossier"] as const;
type Step = (typeof STEPS)[number];

/** The connect step's state: no product view until the connect flow ships (issue 221; owner, A1). */
function ConnectView() {
  const t = useTranslations("landing");
  return <ViewFrame label={t("view.connect.label")}>
    <ul className="lv-body lm-records">{["Microsoft 365", "Google Workspace"].map((name) => <li key={name}>
      <strong>{name}</strong><span className="landing-soon">{t("soon")}</span>
      <span className="lm-line">{t("view.connect.access")}</span>
    </li>)}</ul>
  </ViewFrame>;
}

const VIEWS: Record<Step, () => React.ReactNode> = { connect: ConnectView, assess: MeasureView, routines: RecordsView, dossier: DossierView };

/**
 * "Cómo funciona" (landing-legal amendment A2, issue 356). On wide screens with motion allowed, the
 * steps scroll beside one sticky frame whose stage follows the step in view (IntersectionObserver;
 * no scroll-jacking). The sticky frame is decorative for assistive technology: each step carries its
 * meaning, and on phones or with reduced motion each step shows its own static frame instead.
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
  const pad = (n: number) => String(n).padStart(2, "0");
  return <section className="landing-ink landing-pinned" data-stage={active} aria-labelledby="how-title">
    <div className="landing-ink-inner landing-pinned-grid">
      <div className="landing-pinned-text">
        <h2 id="how-title" className="landing-h2">{t("how.title")}</h2>
        <ol className="landing-steps">{STEPS.map((key, i) => {
          const View = VIEWS[key];
          return <li key={key} data-step={i + 1} ref={(el) => { items.current[i] = el; }}>
            <span className="landing-step-number" aria-hidden="true">{pad(i + 1)}</span>
            <p className="landing-step-title">{t(`how.steps.${key}.title`)}{key === "connect" ? <span className="landing-soon">{t("soon")}</span> : null}</p>
            <p className="landing-step-body">{t(`how.steps.${key}.body`)}</p>
            <div className="landing-step-stage"><View /></div>
          </li>;
        })}</ol>
      </div>
      <div className="landing-stage-frame" aria-hidden="true">
        <p className="landing-stage-counter">{`${pad(active)} / ${pad(STEPS.length)}`}</p>
        <div className="landing-stage-progress"><span /></div>
        <div className="landing-stage-layers">{STEPS.map((key, i) => {
          const View = VIEWS[key];
          return <div key={key} data-stage-view={key} className="landing-stage" data-active={active === i + 1}><View /></div>;
        })}</div>
      </div>
    </div>
  </section>;
}
