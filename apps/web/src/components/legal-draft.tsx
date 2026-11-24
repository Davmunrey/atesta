"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { legalEntity } from "@/content/legal-entity";

type Field = keyof typeof legalEntity | "contact";

/** One draft clause: its heading, the draft mark, its text and any identity fields. */
function Clause({ id, title, body, fields = [], extra }: { id: string; title: string; body: string; fields?: Field[]; extra?: ReactNode }) {
  const t = useTranslations("legal");
  return <section id={id} aria-labelledby={`${id}-title`}>
    <div className="legal-clause-head"><h2 id={`${id}-title`}>{title}</h2><span className="legal-draft-mark">{t("clause")}</span></div>
    <p>{body}</p>
    {fields.length > 0 ? <dl className="storage-list">{fields.map((f) => <div key={f}>
      <dt>{t(`fields.${f}`)}</dt><dd>{f === "contact" ? t("pending") : legalEntity[f]}</dd>
    </div>)}</dl> : null}
    {extra}
  </section>;
}

/**
 * The draft legal pages (landing-legal spec, issue 316): one clause per item the law lists, each
 * marked as a draft, identity only from legal-entity.ts. Spanish is binding; check-legal blocks a
 * release until the owner completes the identity and a lawyer reviews the text.
 */
export function LegalDraft({ page, clauses }: { page: "notice" | "privacy"; clauses: { id: string; fields?: Field[]; extra?: ReactNode }[] }) {
  const t = useTranslations("legal");
  const english = useLocale() === "en";
  return <main id="content" tabIndex={-1} className="policy-page">
    <div className="policy-heading">
      <h1 className="page-title">{t(`${page}.title`)}</h1>
      <p role="note" className="legal-draft-notice">{t("draft")}</p>
      <p>{t(`${page}.intro`)}</p>
      {english ? <p className="text-sm text-muted">{t("binding")}</p> : null}
    </div>
    <div className="policy-layout">
      <nav aria-label={t("index")} className="policy-index">
        <p className="font-medium">{t("index")}</p>
        {clauses.map((c) => <a key={c.id} href={`#${c.id}`}>{t(`${page}.${c.id}.title`)}</a>)}
      </nav>
      <div className="policy-copy">
        {clauses.map((c) => <Clause key={c.id} id={c.id} title={t(`${page}.${c.id}.title`)} body={t(`${page}.${c.id}.body`)} fields={c.fields} extra={c.extra} />)}
      </div>
    </div>
  </main>;
}

export function CookiesLink() {
  const t = useTranslations("cookies");
  return <p><Link href="/cookies" className="text-link underline">{t("title")}</Link></p>;
}
