"use client";

import { useTranslations } from "next-intl";
import { DossierView, MeasureView, RecordsView } from "@/components/landing/moment-views";
import { OverviewView } from "@/components/landing/overview-view";
import { legalEntity } from "@/content/legal-entity";

const MOMENTS = [{ key: "measure", View: MeasureView }, { key: "records", View: RecordsView }, { key: "dossier", View: DossierView }] as const;

/** The public landing (landing-legal spec, L1 and L6): the ENS lead, the product as the argument. */
export default function Landing() {
  const t = useTranslations("landing");
  const request = <a href={`mailto:${legalEntity.email}`} className="landing-cta">{t("requestAccess")}</a>;
  return (
    <main id="content" tabIndex={-1} className="landing">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero-copy">
          <h1 id="landing-title" className="landing-title">{t("headline")}</h1>
          <p className="landing-sub">{t("sub")}</p>
          <div className="landing-actions">{request}</div>
        </div>
        <OverviewView />
      </section>
      {MOMENTS.map(({ key, View }) => <section key={key} className="landing-moment" aria-labelledby={`moment-${key}`}>
        <h2 id={`moment-${key}`} className="landing-moment-title">{t(`moments.${key}`)}</h2>
        <View />
      </section>)}
      <section className="landing-covers" aria-label={t("covers")}>
        <p>{t("covers")}</p>
        <p>{t("consultancies")}</p>
      </section>
      <section className="landing-close" aria-labelledby="landing-close">
        <h2 id="landing-close" className="landing-close-title">{t("close")}</h2>
        <a href={`mailto:${legalEntity.email}`} className="landing-cta landing-cta-ink">{t("requestAccess")}</a>
      </section>
    </main>
  );
}
