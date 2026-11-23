"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import fixture from "@/content/landing-fixture.json";
import { BrandMark } from "../brand-mark";

const FRAMEWORKS = ["NIS2", "RGPD", "LOPDGDD", "DORA"] as const;

/** The frameworks it covers as a slow marquee (amendment A2): a visible pause/play button
 *  (WCAG 2.2.2), paused on hover and focus, still under reduced motion. The second copy that makes
 *  the loop seamless is hidden from assistive technology. */
export function FrameworksStrip() {
  const t = useTranslations("landing");
  const [paused, setPaused] = useState(false);
  const items = (copy: boolean) => <ul className="landing-frameworks" aria-hidden={copy || undefined}>
    <li className="landing-framework-lead"><BrandMark /> {fixture.framework}</li>
    {FRAMEWORKS.map((name) => <li key={name}>{name} <span className="landing-soon landing-by-plan">{t("frameworks.byPlan")}</span></li>)}
  </ul>;
  return <div className="landing-marquee" data-paused={paused}>
    <div className="landing-marquee-window"><div className="landing-marquee-track">{items(false)}{items(true)}</div></div>
    <button type="button" className="dashboard-button landing-marquee-toggle" aria-pressed={paused} onClick={() => setPaused(!paused)}>
      {t("marquee.pause")}
    </button>
  </div>;
}
