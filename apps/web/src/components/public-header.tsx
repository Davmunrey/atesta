"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { legalEntity } from "@/content/legal-entity";
import { BrandMark } from "./brand-mark";
import { LocaleSwitcher } from "./locale-switcher";

/** The header every public page shares (ui-polish spec, issue 301): skip link, wordmark home and
 *  the language switcher. Each public page's main element carries id="content". The landing adds
 *  sign-in and the access request (landing-legal spec, issue 308). */
export function PublicHeader() {
  const t = useTranslations("cookies");
  const brand = useTranslations("brand");
  const app = useTranslations("app");
  const landing = useTranslations("landing");
  const locale = useLocale();
  const onLanding = usePathname() === "/";
  return <header className="document-header">
    <a href="#content" className="skip-link">{app("skipContent")}</a>
    <Link href="/" className="brand-lockup" aria-label={t("home", { brand: brand("name") })}><BrandMark /><span className="brand-word">{brand("name")}</span></Link>
    <div className="public-header-end">
      <LocaleSwitcher />
      {onLanding ? <nav aria-label={landing("signIn")} className="public-header-actions">
        <a href={`/auth/login?lang=${locale}`} className="landing-signin">{landing("signIn")}</a>
        <a href={`mailto:${legalEntity.email}`} className="landing-cta">{landing("requestAccess")}</a>
      </nav> : null}
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
