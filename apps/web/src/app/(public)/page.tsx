"use client";

import { useTranslations } from "next-intl";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { BrandMark } from "@/components/brand-mark";
import { FrameworksStrip } from "@/components/landing/frameworks-strip";
import { OverviewView } from "@/components/landing/overview-view";
import { PinnedSteps } from "@/components/landing/pinned-steps";
import { YearOfEns } from "@/components/landing/year-of-ens";
import { legalEntity } from "@/content/legal-entity";


/** The public landing (landing-legal spec, L1-L7 and amendment A1): the ENS lead, the
 *  product as the argument, one brand system (mark, highlighter motif, paper and ink). */
export default function Landing() {
  const t = useTranslations("landing");
  const mail = `mailto:${legalEntity.email}`;
  return (
    <main id="content" tabIndex={-1} className="landing">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <h1 id="landing-title" className="landing-title">{t.rich("headline", { hl: (chunks) => <mark className="hl">{chunks}</mark> })}</h1>
          <p className="landing-sub">{t("sub")}</p>
          <div className="landing-actions"><a href={mail} className="landing-cta">{t("requestAccess")}</a></div>
        </div>
        <OverviewView />
      </section>

      <section className="landing-band landing-problem" aria-labelledby="problem-title">
        <h2 id="problem-title" className="landing-h2">{t("problem.title")}</h2>
        <p className="landing-statement">{t("problem.body")}</p>
      </section>

      <PinnedSteps />

      <YearOfEns />

      <section className="landing-band" aria-labelledby="frameworks-title">
        <h2 id="frameworks-title" className="landing-h2">{t("frameworks.title")}</h2>
        <p className="landing-statement">{t("frameworks.body")}</p>
        <FrameworksStrip />
        <p className="landing-consultancies">{t("consultancies")}</p>
      </section>

      <section className="landing-close" aria-labelledby="landing-close">
        <BrandMark className="landing-close-seal" />
        <h2 id="landing-close" className="landing-close-title">{t("close")}</h2>
        <a href={mail} className="landing-cta landing-cta-ink">{t("requestAccess")}</a>
      </section>
      <AssistantLauncher surface="landing" />
    </main>
  );
}
