"use client";

import { useTranslations } from "next-intl";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { BrandMark } from "@/components/brand-mark";
import { FrameworksStrip } from "@/components/landing/frameworks-strip";
import { FrameworksRing } from "@/components/landing/frameworks-ring";
import { HeroTabs } from "@/components/landing/hero-tabs";
import { PinnedSteps } from "@/components/landing/pinned-steps";
import { YearOfEns } from "@/components/landing/year-of-ens";
import { ProofStrip } from "@/components/public/proof-strip";
import { legalEntity } from "@/content/legal-entity";


/** Connectors to come (A3): product names as text until each vendor's logo guidelines are read. */
const CONNECTORS = ["Microsoft 365", "Google Workspace"] as const;

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
          <div className="landing-actions"><a href={mail} className="landing-cta">{t("requestAccess")}</a><a href="#how-title" className="landing-signin">{t("more")}</a></div>
        </div>
        <HeroTabs />
      </section>

      <section className="landing-proof" aria-label={t("connects")}>
        <ProofStrip />
        <p className="landing-connects"><span>{t("connects")}</span>{CONNECTORS.map((name) => <span key={name} className="landing-connector"><strong>{name}</strong> <span className="landing-soon">{t("soon")}</span></span>)}</p>
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
        <FrameworksRing />
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
