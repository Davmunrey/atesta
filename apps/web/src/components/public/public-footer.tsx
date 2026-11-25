"use client";

import { useTranslations } from "next-intl";
import { legalEntity } from "@/content/legal-entity";
import { BrandMark } from "@atesta/ui/brand-mark";
import { DOCS, LINKS, PAGES } from "./site-map";

/** The public footer (A3): a full map of the public site on ink, with the honest proof. Plain
 *  anchors, so navigations are document loads that View Transitions can morph. */
export function PublicFooter() {
  const t = useTranslations("public");
  const brand = useTranslations("brand");
  const legal = useTranslations("footer");
  const cookies = useTranslations("cookies");
  return <footer className="public-footer">
    <div className="public-footer-inner">
      <div className="public-footer-brand">
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- a document load lets View Transitions morph the page (A3) */}
        <a href="/" className="brand-lockup public-footer-lockup"><BrandMark /><span className="brand-word">{brand("name")}</span></a>
        <p>{t("footer.tagline")}</p>
        <p><a href={`mailto:${legalEntity.email}`} className="public-footer-link">{legalEntity.email}</a></p>
      </div>
      <nav className="public-footer-map" aria-label={legal("label")}>
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- a document load lets View Transitions morph the page (A3) */}
        <div><h2>{t("footer.product")}</h2><ul>{PAGES.producto ? <li><a href="/producto">{t("nav.product")}</a></li> : null}<li><a href="/#how-title">{t("footer.how")}</a></li>
          {LINKS.map((l) => <li key={l.key}><a href={l.href}>{t(`nav.${l.key}`)}</a></li>)}</ul></div>
        <div><h2>{t("footer.resources")}</h2><ul>{DOCS.map((d) => <li key={d.key}><a href={d.href}>{t(`nav.items.${d.key}.title`)}</a></li>)}</ul></div>
        <div><h2>{t("footer.legal")}</h2><ul>
          <li><a href="/aviso-legal">{legal("notice")}</a></li><li><a href="/privacidad">{legal("privacy")}</a></li><li><a href="/cookies">{cookies("title")}</a></li></ul></div>
      </nav>
    </div>
  </footer>;
}
