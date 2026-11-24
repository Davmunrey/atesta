"use client";

import { useTranslations } from "next-intl";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { BrandMark } from "@/components/brand-mark";
import { FrameworkMappingTable } from "@/components/framework-mapping";
import { PAGES } from "@/components/public/site-map";
import { legalEntity } from "@/content/legal-entity";
import type { LandingCatalog } from "@/lib/catalog/landing";
import { MeasureView } from "./moment-views";
import { PinnedSteps } from "./pinned-steps";

/**
 * The public landing (landing-legal spec L1-L7; amendment A4, issue 393): the story told once. The
 * hero shows one ENS measure as the console shows it, its official text read from the catalog; the
 * steps carry the product views; one mapping table stands for the other frameworks.
 */
export function LandingPage({ catalog }: { catalog: LandingCatalog }) {
  const t = useTranslations("landing");
  const mail = `mailto:${legalEntity.email}`;
  return (
    <main id="content" tabIndex={-1} className="landing">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <h1 id="landing-title" className="landing-title">{t.rich("headline", { hl: (chunks) => <mark className="hl">{chunks}</mark> })}</h1>
          <div>
            <p className="landing-sub">{t("sub")}</p>
            <div className="landing-actions"><a href={mail} className="landing-cta">{t("requestAccess")}</a><a href="#how-title" className="landing-signin">{t("more")}</a></div>
          </div>
        </div>
        <MeasureView measure={catalog.measure} />
      </section>

      <section className="landing-band landing-split" aria-labelledby="problem-title">
        <h2 id="problem-title" className="landing-h2">{t("problem.title")}</h2>
        <p className="landing-statement">{t("problem.body")}</p>
      </section>

      <PinnedSteps />

      <section className="landing-band landing-split" aria-labelledby="frameworks-title">
        <div className="landing-band-copy">
          <h2 id="frameworks-title" className="landing-h2">{t("frameworks.title")}</h2>
          <p className="landing-statement">{t("frameworks.body")}</p>
        </div>
        <FrameworkMappingTable mapping={catalog.mapping} />
        <p className="landing-consultancies">{t("frameworks.consultancies")}{PAGES.consultoras
          ? <> <a href="/consultoras" className="landing-signin">{t("frameworks.consultanciesLink")}</a></> : null}</p>
      </section>

      <section className="landing-close" aria-labelledby="landing-close">
        <BrandMark className="landing-close-seal" />
        <h2 id="landing-close" className="landing-close-title">{t("close.title")}</h2>
        <p className="landing-close-body">{t("close.body")}</p>
        <a href={mail} className="landing-cta landing-cta-ink">{t("requestAccess")}</a>
      </section>
      <AssistantLauncher surface="landing" />
    </main>
  );
}
