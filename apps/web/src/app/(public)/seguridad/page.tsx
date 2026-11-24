"use client";

import { useTranslations } from "next-intl";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { BrandMark } from "@/components/brand-mark";
import { PageIndex } from "@/components/public/page-index";
import { legalEntity } from "@/content/legal-entity";

/** Connectors to come (A3): names as text until each vendor's logo guidelines are read. */
const CONNECTORS = ["Microsoft 365", "Google Workspace"] as const;
const STORED = ["s1", "s2", "s3", "s4"] as const;
const NEVER = ["n1", "n2", "n3"] as const;
const RULES = ["readonly", "isolation", "secrets", "audit", "ai"] as const;

/** /seguridad (landing-legal amendment A3, issue 381). Every statement traces to SECURITY.md or an
 *  ADR; hosting is not live, so the region is "designed to be deployed" (owner, 2026-11-23). */
export default function Seguridad() {
  const t = useTranslations("seguridad");
  const landing = useTranslations("landing");
  const mail = `mailto:${legalEntity.email}`;
  return (
    <main id="content" tabIndex={-1} className="landing security-page">
      <section className="page-hero" aria-labelledby="seguridad-title">
        <div className="page-hero-copy">
          <h1 id="seguridad-title" className="landing-title">{t.rich("title", { hl: (chunks) => <mark className="hl">{chunks}</mark> })}</h1>
          <p className="landing-sub">{t("sub")}</p>
          <p className="page-status">{t("status")}</p>
        </div>
        <PageIndex items={[{ id: "datos", label: t("region.title") }, { id: "guardamos", label: t("data.title") }, { id: "reglas", label: t("rules.title") }]} />
      </section>

      <section className="page-band sec-touch">
        <figure className="sec-diagram" aria-label={t("diagram.label")}>
          <ol className="sec-flow">
            <li className="sec-node">
              <p className="sec-node-title">{t("diagram.systems")}</p>
              <ul className="sec-systems">{CONNECTORS.map((name) => <li key={name}><strong>{name}</strong> <span className="landing-soon">{landing("soon")}</span></li>)}</ul>
            </li>
            <li className="sec-edge"><span>{t("diagram.read")}</span></li>
            <li className="sec-node">
              <p className="sec-node-title">{t("diagram.scanner")}</p>
              <p className="sec-node-note">{t("diagram.scannerNote")}</p>
            </li>
            <li className="sec-edge"><span>{t("diagram.strip")}</span></li>
            <li className="sec-node sec-node-ink">
              <p className="sec-node-title"><BrandMark className="sec-seal" />{t("diagram.atesta")}</p>
              <p className="sec-node-note">{t("diagram.atestaNote")}</p>
            </li>
          </ol>
          <figcaption className="sec-never">{t("diagram.write")}</figcaption>
        </figure>
      </section>

      <section id="datos" className="page-band sec-split" aria-labelledby="datos-title">
        <h2 id="datos-title" className="landing-h2">{t("region.title")}</h2>
        <p className="product-body">{t("region.body")}</p>
      </section>

      <section id="guardamos" className="page-band sec-split" aria-labelledby="guardamos-title">
        <div className="page-band-copy">
          <h2 id="guardamos-title" className="landing-h2">{t("data.title")}</h2>
          <p className="lv-legend">{t("data.retention")}</p>
        </div>
        <div className="sec-lists">
          <div><h3 className="sec-list-title">{t("data.stored")}</h3><ul className="product-points">{STORED.map((k) => <li key={k}>{t(`data.${k}`)}</li>)}</ul></div>
          <div><h3 className="sec-list-title">{t("data.never")}</h3><ul className="product-points sec-never-list">{NEVER.map((k) => <li key={k}>{t(`data.${k}`)}</li>)}</ul></div>
        </div>
      </section>

      <section id="reglas" className="page-band" aria-labelledby="reglas-title">
        <div className="page-band-copy">
          <h2 id="reglas-title" className="landing-h2">{t("rules.title")}</h2>
          <p className="product-body">{t("rules.body")}</p>
        </div>
        <dl className="sec-rules">{RULES.map((k) => <div key={k}><dt>{t(`rules.${k}.name`)}</dt><dd>{t(`rules.${k}.how`)}</dd></div>)}</dl>
      </section>

      <section className="landing-close" aria-labelledby="seguridad-close">
        <BrandMark className="landing-close-seal" />
        <h2 id="seguridad-close" className="landing-close-title">{t("report.title")}</h2>
        <p className="sec-report">{t("report.body", { email: legalEntity.email })}</p>
        <a href={mail} className="landing-cta landing-cta-ink">{legalEntity.email}</a>
      </section>
      <AssistantLauncher surface="landing" />
    </main>
  );
}
