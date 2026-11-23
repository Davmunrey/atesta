"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useId, useRef, useState } from "react";
import { legalEntity } from "@/content/legal-entity";
import { BrandMark } from "./brand-mark";
import { LocaleSwitcher } from "./locale-switcher";
import { DOCS, LINKS, type MenuItem, PRODUCT } from "./public/site-map";

type Panel = "product" | "docs" | "menu" | null;

function Item({ item }: { item: MenuItem }) {
  const t = useTranslations("public.nav.items");
  return <a href={item.href} className="mega-link"><span>{t(`${item.key}.title`)}</span><small>{t(`${item.key}.desc`)}</small></a>;
}

/**
 * The header every public page shares (ui-polish issue 301; landing-legal A3, issue 371): skip link,
 * lockup, the product and docs menus as disclosures (Esc and an outside click close them), the
 * language switcher and the two actions. It hides on scroll down and returns on scroll up, never
 * under reduced motion or while a menu is open. Below 64rem everything sits in one "Menú" panel.
 * Each public main element carries id="content".
 */
export function PublicHeader() {
  const t = useTranslations("public.nav");
  const cookies = useTranslations("cookies");
  const brand = useTranslations("brand");
  const app = useTranslations("app");
  const landing = useTranslations("landing");
  const locale = useLocale();
  const id = useId();
  const [open, setOpen] = useState<Panel>(null);
  const [hidden, setHidden] = useState(false);
  const header = useRef<HTMLElement>(null);
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && open) { buttons.current[open]?.focus(); setOpen(null); } };
    const onDown = (e: PointerEvent) => { if (open && !header.current?.contains(e.target as Node)) setOpen(null); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onDown); };
  }, [open]);
  useEffect(() => {
    if (typeof window.matchMedia !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      setHidden(y > last && y > 160 && !header.current?.contains(document.activeElement));
      last = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const toggle = (panel: Exclude<Panel, null>) => setOpen(open === panel ? null : panel);
  const disclosure = (panel: "product" | "docs" | "menu", label: string, extra = "") => <button type="button" ref={(el) => { buttons.current[panel] = el; }}
    className={`mega-trigger${extra}`} aria-expanded={open === panel} aria-controls={`${id}-${panel}`} onClick={() => toggle(panel)}>{label}</button>;
  const productPanel = <div className="mega-groups">{PRODUCT.map((g) => <div key={g.group}><p className="mega-group">{t(`groups.${g.group}`)}</p>{g.items.map((i) => <Item key={i.key} item={i} />)}</div>)}
    <p className="mega-feature">{t("feature")}</p></div>;
  const actions = <div className="public-header-actions">
    <a href={`/auth/login?lang=${locale}`} className="landing-signin">{landing("signIn")}</a>
    <a href={`mailto:${legalEntity.email}`} className="landing-cta">{landing("requestAccess")}</a>
  </div>;
  return <header ref={header} className="document-header public-site-header" data-hidden={hidden && open === null}>
    <a href="#content" className="skip-link">{app("skipContent")}</a>
    {/* eslint-disable-next-line @next/next/no-html-link-for-pages -- a document load lets View Transitions morph the page (A3) */}
    <a href="/" className="brand-lockup" aria-label={cookies("home", { brand: brand("name") })}><BrandMark /><span className="brand-word">{brand("name")}</span></a>
    <nav className="public-nav" aria-label={t("label")}>
      <ul>
        <li>{disclosure("product", t("product"))}</li>
        {LINKS.map((l) => <li key={l.key}><a href={l.href} className="public-nav-link">{t(l.key)}</a></li>)}
        <li>{disclosure("docs", t("docs"))}</li>
      </ul>
    </nav>
    <div className="public-header-end">
      <span className="public-locale"><LocaleSwitcher /></span>
      {actions}
      {disclosure("menu", t("menu"), " public-menu-trigger")}
    </div>
    <div id={`${id}-product`} className="mega-panel" hidden={open !== "product"}>{productPanel}</div>
    <div id={`${id}-docs`} className="mega-panel" hidden={open !== "docs"}><div className="mega-groups">{DOCS.map((d) => <Item key={d.key} item={d} />)}</div></div>
    <div id={`${id}-menu`} className="mega-panel public-menu-panel" hidden={open !== "menu"}>
      {productPanel}
      <div className="mega-groups">{DOCS.map((d) => <Item key={d.key} item={d} />)}{LINKS.map((l) => <a key={l.key} href={l.href} className="mega-link"><span>{t(l.key)}</span></a>)}</div>
      <div className="public-menu-end"><LocaleSwitcher />{actions}</div>
    </div>
  </header>;
}

/** A link a person opened that cannot be used: a heading and one sentence on what to do. */
export function LinkProblem({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="flex flex-col gap-4">
    <h1 className="page-title">{title}</h1>
    <p role="alert">{children}</p>
  </section>;
}
