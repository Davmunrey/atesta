"use client";

import { useTranslations } from "next-intl";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { PublicHeader } from "@/components/public-header";
import { PublicCard } from "@/components/public/public-card";
import { PublicFooter } from "@/components/public/public-footer";

/** Replaces Next's default 404, whose inline styles the CSP (style-src 'self') would block. In the
 *  public style (A3, issue 384): a card with the seal, what may have happened, a way into the
 *  assistant and the pages a visitor most likely wanted. */
export default function NotFound() {
  const t = useTranslations("notFound");
  const nav = useTranslations("public.nav");
  return (
    <div className="public-surface flex min-h-dvh flex-col bg-bg text-fg">
      <PublicHeader />
      <main id="content" tabIndex={-1} className="public-card-page">
        <PublicCard>
          <h1 className="page-title">{t("title")}</h1>
          <p>{t("body")}</p>
          <div><AssistantLauncher surface="landing" invite={t("ask")} /></div>
          <p className="text-muted">{t("also")}</p>
          {/* eslint-disable @next/next/no-html-link-for-pages -- document loads let View Transitions morph the page (A3) */}
          <ul className="public-card-links">
            <li><a href="/">{t("home")}</a></li>
            <li><a href="/producto">{nav("product")}</a></li>
            <li><a href="/ens">{nav("ens")}</a></li>
          </ul>
          {/* eslint-enable @next/next/no-html-link-for-pages */}
        </PublicCard>
      </main>
      <PublicFooter />
    </div>
  );
}
