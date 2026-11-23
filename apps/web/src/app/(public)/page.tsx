"use client";

import { useTranslations } from "next-intl";
import { BrandMark } from "@/components/brand-mark";
import { DossierView, MeasureView, RecordsView } from "@/components/landing/moment-views";
import { OverviewView } from "@/components/landing/overview-view";
import fixture from "@/content/landing-fixture.json";
import { legalEntity } from "@/content/legal-entity";

const MOMENTS = [{ key: "measure", View: MeasureView }, { key: "records", View: RecordsView }, { key: "dossier", View: DossierView }] as const;
const STEPS = [["connect", true], ["assess", false], ["routines", false], ["dossier", false]] as const;
const FRAMEWORKS = ["NIS2", "RGPD", "LOPDGDD", "DORA"] as const;

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

      <section className="landing-ink" aria-labelledby="how-title">
        <div className="landing-ink-inner">
        <h2 id="how-title" className="landing-h2">{t("how.title")}</h2>
        <ol className="landing-steps">{STEPS.map(([key, soon], i) => <li key={key}>
          <span className="landing-step-number" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
          <p className="landing-step-title">{t(`how.steps.${key}.title`)}{soon ? <span className="landing-soon">{t("soon")}</span> : null}</p>
          <p className="landing-step-body">{t(`how.steps.${key}.body`)}</p>
        </li>)}</ol>
        </div>
      </section>

      {MOMENTS.map(({ key, View }) => <section key={key} className="landing-band landing-moment" aria-labelledby={`moment-${key}`}>
        <h2 id={`moment-${key}`} className="landing-moment-title">{t(`moments.${key}`)}</h2>
        <View />
      </section>)}

      <section className="landing-band" aria-labelledby="frameworks-title">
        <h2 id="frameworks-title" className="landing-h2">{t("frameworks.title")}</h2>
        <p className="landing-statement">{t("frameworks.body")}</p>
        <ul className="landing-frameworks">
          <li className="landing-framework-lead"><BrandMark /> {fixture.framework}</li>
          {FRAMEWORKS.map((name) => <li key={name}>{name} <span className="landing-soon landing-by-plan">{t("frameworks.byPlan")}</span></li>)}
        </ul>
        <p className="landing-consultancies">{t("consultancies")}</p>
      </section>

      <section className="landing-close" aria-labelledby="landing-close">
        <BrandMark className="landing-close-seal" />
        <h2 id="landing-close" className="landing-close-title">{t("close")}</h2>
        <a href={mail} className="landing-cta landing-cta-ink">{t("requestAccess")}</a>
      </section>
    </main>
  );
}
