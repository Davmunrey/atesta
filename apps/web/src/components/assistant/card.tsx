"use client";

import { useLocale, useTranslations } from "next-intl";
import { orgLink, pick } from "@/lib/assistant/flows";
import type { Locale } from "@atesta/ui/i18n/locale";
import type { Citation, Doc, Text } from "@/lib/assistant/types";

/** One cited source line (assistant spec): official text links to BOE or EUR-Lex. */
export function Cite({ cite }: { cite: Citation }) {
  const t = useTranslations("assistant.cite");
  if (cite.kind === "guide") return <span>{t("guide", { guide: cite.guide, edition: cite.edition, section: cite.section, page: cite.page })}</span>;
  if (cite.kind === "faq") return <span>{t("faq")} · {cite.id}{cite.reviewed ? null : <span className="assistant-pending">{t("pending")}</span>}</span>;
  return (
    <span>
      {cite.frameworkName} · <span className="font-mono">{cite.code}</span>
      {cite.section ? <>, {t("section", { section: cite.section })}</> : null}
      {" · "}<a href={cite.url} className="text-link underline" target="_blank" rel="noopener noreferrer">{t("official")}</a>
    </span>
  );
}

export function Cites({ cites }: { cites: Citation[] }) {
  const t = useTranslations("assistant.cite");
  return (
    <footer className="assistant-cite">
      {cites.map((cite, n) => <p key={n}>{t("label")} <Cite cite={cite} /></p>)}
    </footer>
  );
}

/** Verbatim text; Spanish-only text in the English interface carries lang="es". */
export function Quote({ text, as = "blockquote" }: { text: Text; as?: "blockquote" | "p" | "span" }) {
  const shown = pick(text, useLocale() as Locale);
  if (!shown) return null;
  const Tag = as;
  return <Tag lang={shown.lang} className={as === "blockquote" ? "assistant-quote" : undefined}>{shown.value}</Tag>;
}

const LONG = 600;

/** An answer card: what kind of content, the quote, its items and every citation. */
export function AnswerCard({ doc, orgId, open = false }: { doc: Doc; orgId?: string | null; open?: boolean }) {
  const t = useTranslations("assistant");
  const locale = useLocale() as Locale;
  const title = pick(doc.title, locale);
  const body = pick(doc.text, locale);
  const link = orgLink(doc, orgId);
  return (
    <article className="assistant-card" aria-labelledby={`card-${doc.id}`}>
      <header>
        <p className="assistant-kind">{t(`kind.${doc.kind}`)}</p>
        <h3 id={`card-${doc.id}`} className="assistant-card-title">
          {doc.code ? <span className="font-mono">{doc.code} </span> : null}
          {title ? <span lang={title.lang}>{title.value}</span> : null}
        </h3>
      </header>
      {body && body.value.length > LONG
        ? <details className="assistant-more" open={open}><summary>{t("fullText")}</summary><Quote text={doc.text} /></details>
        : <Quote text={doc.text} />}
      {doc.items.length > 0 ? <ul className="assistant-items">{doc.items.map((item, n) => <li key={n}><Quote text={item.text} as="span" /></li>)}</ul> : null}
      {link ? <p><a href={link} className="text-link underline">{t("inOrg")}</a></p> : null}
      <Cites cites={doc.cite} />
    </article>
  );
}
