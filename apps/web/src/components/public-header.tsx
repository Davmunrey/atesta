"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { LocaleSwitcher } from "./locale-switcher";

/** The header every public page shares (ui-polish spec, issue 301): skip link, wordmark home and
 *  the language switcher. Each public page's main element carries id="content". */
export function PublicHeader() {
  const t = useTranslations("cookies");
  const brand = useTranslations("brand");
  const app = useTranslations("app");
  return <header className="document-header">
    <a href="#content" className="skip-link">{app("skipContent")}</a>
    <Link href="/" className="brand-mark" aria-label={t("home", { brand: brand("name") })}>{brand("name")}</Link>
    <LocaleSwitcher />
  </header>;
}

/** A link a person opened that cannot be used: a heading and one sentence on what to do. */
export function LinkProblem({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="flex flex-col gap-4">
    <h1 className="page-title">{title}</h1>
    <p role="alert">{children}</p>
  </section>;
}
