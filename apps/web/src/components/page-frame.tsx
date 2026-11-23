"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { type ReactNode, useId } from "react";

export type Crumb = { label: string; href?: string };

export function Breadcrumbs({ crumbs }: { crumbs: Crumb[] }) {
  const t = useTranslations("console");
  return <nav aria-label={t("breadcrumbs")} className="breadcrumbs">
    <ol>{crumbs.map((c, i) => <li key={`${c.label}-${i}`}>
      {c.href && i < crumbs.length - 1 ? <Link href={c.href}>{c.label}</Link> : <span aria-current={i === crumbs.length - 1 ? "page" : undefined}>{c.label}</span>}
    </li>)}</ol>
  </nav>;
}

/** Breadcrumbs and the page header every console page starts with (console-shell spec). */
export function PageHeader({ crumbs = [], title, description, actions }: { crumbs?: Crumb[]; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return <div className="page-header">
    {crumbs.length > 0 ? <Breadcrumbs crumbs={crumbs} /> : null}
    <div className="page-header-row">
      <div className="page-header-text">
        <h1 className="page-title">{title}</h1>
        {description ? <div className="page-description">{description}</div> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </div>
  </div>;
}

/** A titled container; panels never nest (console-shell spec). */
export function Panel({ title, description, actions, children, className }: { title?: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  const id = useId();
  return <section className={`panel${className ? ` ${className}` : ""}`} aria-labelledby={title ? id : undefined}>
    {title ? <header className="panel-header">
      <div><h2 id={id} className="panel-title">{title}</h2>{description ? <p className="panel-description">{description}</p> : null}</div>
      {actions ? <div className="panel-actions">{actions}</div> : null}
    </header> : null}
    <div className="panel-body">{children}</div>
  </section>;
}
