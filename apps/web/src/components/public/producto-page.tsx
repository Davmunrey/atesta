"use client";

import { useTranslations } from "next-intl";
import type { ComponentType } from "react";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { BrandMark } from "@/components/brand-mark";
import { ApiView, AssistantView, DossierView, IncidentView, MeasureView, RecordsView } from "@/components/landing/moment-views";
import { PageIndex } from "@/components/public/page-index";
import { legalEntity } from "@/content/legal-entity";
import type { HeroMeasure } from "@/lib/catalog/landing";

/** One section per capability, at the anchors the header menus use (A3, issue 377). */
const SECTIONS: [id: string, key: string, View: ComponentType<{ measure: HeroMeasure }>][] = [
  ["autoevaluacion", "assess", MeasureView],
  ["registros", "routines", RecordsView],
  ["incidentes", "incidents", IncidentView],
  ["dossier", "dossier", DossierView],
  ["asistente", "assistant", AssistantView],
  ["api", "api", ApiView],
];
const POINTS = ["p1", "p2", "p3"] as const;

/** /producto (landing-legal amendment A3): each capability with its product view. The
 *  self-assessment is the shared measure sheet the landing's hero shows (A4). */
export function ProductoPage({ measure }: { measure: HeroMeasure }) {
  const t = useTranslations("producto");
  const landing = useTranslations("landing");
  const nav = useTranslations("public.nav.items");
  const mail = `mailto:${legalEntity.email}`;
  return (
    <main id="content" tabIndex={-1} className="landing product-page">
      <section className="page-hero" aria-labelledby="producto-title">
        <div className="page-hero-copy">
          <h1 id="producto-title" className="landing-title">{t.rich("title", { hl: (chunks) => <mark className="hl">{chunks}</mark> })}</h1>
          <p className="landing-sub">{t("sub")}</p>
          <div className="landing-actions"><a href={mail} className="landing-cta">{landing("requestAccess")}</a><a href="/ens" className="landing-signin">{t("ens")}</a></div>
        </div>
        <PageIndex items={SECTIONS.map(([id, key]) => ({ id, label: nav(`${key}.title`) }))} />
      </section>

      {SECTIONS.map(([id, key, View]) => (
        <section key={id} id={id} className="product-section" aria-labelledby={`${id}-title`}>
          <div className="product-copy">
            <h2 id={`${id}-title`} className="landing-h2">{t(`${key}.title`)}</h2>
            <p className="product-body">{t(`${key}.body`)}</p>
            <ul className="product-points">{POINTS.map((p) => <li key={p}>{t(`${key}.${p}`)}</li>)}</ul>
          </div>
          <div className="product-view"><View measure={measure} /></div>
        </section>
      ))}

      <section className="landing-close" aria-labelledby="producto-close">
        <BrandMark className="landing-close-seal" />
        <h2 id="producto-close" className="landing-close-title">{t("close")}</h2>
        <a href={mail} className="landing-cta landing-cta-ink">{landing("requestAccess")}</a>
      </section>
      <AssistantLauncher surface="landing" />
    </main>
  );
}
