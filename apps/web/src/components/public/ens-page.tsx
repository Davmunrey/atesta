"use client";

import { useTranslations } from "next-intl";
import { type ReactNode, useEffect, useState } from "react";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { CategoryFlow } from "@/components/assistant/flows";
import { BrandMark } from "@atesta/ui/brand-mark";
import { PageIndex } from "@/components/public/page-index";
import { legalEntity } from "@/content/legal-entity";
import { loadIndex } from "@/lib/assistant/flows";
import type { Index } from "@/lib/assistant/types";
import type { EnsCatalog } from "@/lib/catalog/ens";

type Load = { kind: "loading" } | { kind: "ready"; index: Index } | { kind: "error" };

/** The assistant's own category flow, inline (A3, issue 377): same static index, same citations.
 *  A failed load leaves the rest of the page usable. */
function CategoryChooser() {
  const t = useTranslations("ens.chooser");
  const [state, setState] = useState<Load>({ kind: "loading" });
  const [status, setStatus] = useState("");
  useEffect(() => {
    let live = true;
    loadIndex().then((index) => live && setState({ kind: "ready", index }), () => live && setState({ kind: "error" }));
    return () => { live = false; };
  }, []);
  return <div className="assistant-body ens-flow">
    {state.kind === "ready" ? <CategoryFlow index={state.index} announce={setStatus} />
      : state.kind === "error" ? <p role="alert">{t("error")}</p>
        : <p className="text-muted">{t("loading")}</p>}
    <p className="sr-only" role="status">{status}</p>
  </div>;
}

const rule = (value: string) => (value === "aplica" ? "applies" : value === "n.a." ? "none" : "reinforced");

/** /ens (landing-legal amendment A3): the ENS, its categories and its 73 measures, every official
 *  word read from the catalog pack at build time (CLAUDE.md rule 10). */
export function EnsPage({ catalog }: { catalog: EnsCatalog }) {
  const t = useTranslations("ens");
  const landing = useTranslations("landing");
  const mail = `mailto:${legalEntity.email}`;
  const total = catalog.frameworks.reduce((n, f) => n + f.groups.reduce((m, g) => m + g.measures.length, 0), 0);
  const es = (chunks: ReactNode) => <strong lang="es">{chunks}</strong>;
  return (
    <main id="content" tabIndex={-1} className="landing ens-page">
      <section className="page-hero" aria-labelledby="ens-title">
        <div className="page-hero-copy">
          <h1 id="ens-title" className="landing-title">{t.rich("title", { hl: (chunks) => <mark className="hl">{chunks}</mark> })}</h1>
          <p className="landing-sub">{t("sub")}</p>
          <div className="landing-actions"><a href={mail} className="landing-cta">{landing("requestAccess")}</a><a href={catalog.source} className="landing-signin">{t("source")}</a></div>
        </div>
        <PageIndex items={[{ id: "categorias", label: t("categories.title") }, { id: "categoria", label: t("chooser.title") }, { id: "medidas", label: t("measures.title", { count: total }) }]} />
      </section>

      <section id="categorias" className="page-band ens-categories" aria-labelledby="categories-title">
        <div className="page-band-copy">
          <h2 id="categories-title" className="landing-h2">{t("categories.title")}</h2>
          <p className="product-body">{t("categories.body")}</p>
        </div>
        <ol className="ens-scale">{catalog.columns.map((column) => {
          const [category = "", level = ""] = column.split(" · ");
          return <li key={column} data-category={category}><span>{t.rich("categories.step", { level, category, l: es, c: es })}</span></li>;
        })}</ol>
      </section>

      <section id="categoria" className="page-band ens-chooser" aria-labelledby="chooser-title">
        <div className="page-band-copy">
          <h2 id="chooser-title" className="landing-h2">{t("chooser.title")}</h2>
          <p className="product-body">{t("chooser.body")}</p>
          <p className="lv-legend">{t("chooser.note")}</p>
        </div>
        <CategoryChooser />
      </section>

      <section id="medidas" className="page-band ens-measures" aria-labelledby="measures-title">
        <div className="page-band-copy">
          <h2 id="measures-title" className="landing-h2">{t("measures.title", { count: total })}</h2>
          <p className="product-body">{t("measures.body")}</p>
        </div>
        <div className="ens-frameworks">{catalog.frameworks.map((framework, f) => (
          <div key={framework.prefix} className="ens-framework">
            <h3 className="ens-framework-title"><span className="lv-code">{framework.prefix}</span> <span lang="es">{framework.title}</span></h3>
            {framework.groups.map((group, g) => (
              <details key={group.prefix} className="ens-group" open={f === 0 && g === 0}>
                <summary>{group.prefix === framework.prefix ? null : <><span className="lv-code">{group.prefix}</span> <span lang="es">{group.title}</span> </>}<span className="ens-count">{t("measures.count", { count: group.measures.length })}</span></summary>
                <div className="table-region ens-table" role="region" tabIndex={0} aria-label={`${group.prefix} · ${group.title}`}>
                  <table>
                    <thead><tr>
                      <th scope="col">{t("measures.code")}</th><th scope="col">{t("measures.measure")}</th><th scope="col">{t("measures.dimensions")}</th>
                      {catalog.columns.map((column) => <th key={column} scope="col" lang="es">{column}</th>)}
                    </tr></thead>
                    <tbody>{group.measures.map((m) => (
                      <tr key={m.code}>
                        <th scope="row"><a href={m.source} className="lv-code">{m.code}</a></th>
                        <td lang="es">{m.title}</td>
                        <td lang="es" data-label={t("measures.dimensions")}>{m.dimensions}</td>
                        {m.rules.map((value, n) => <td key={n} lang="es" data-rule={rule(value)} data-label={catalog.columns[n]}>{value}</td>)}
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              </details>
            ))}
          </div>
        ))}</div>
      </section>

      <section className="landing-close" aria-labelledby="ens-close">
        <BrandMark className="landing-close-seal" />
        <h2 id="ens-close" className="landing-close-title">{t("close")}</h2>
        <div className="landing-actions"><a href={mail} className="landing-cta landing-cta-ink">{landing("requestAccess")}</a><a href="/producto" className="landing-signin">{t("product")}</a></div>
      </section>
      <AssistantLauncher surface="landing" />
    </main>
  );
}
