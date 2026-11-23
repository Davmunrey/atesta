"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { Operation } from "@/lib/api-reference";
import { type Scope, SCOPES } from "@/lib/api/tokens";

const ERRORS = [
  ["identity.api_token_invalid", 401],
  ["identity.token_in_query", 400],
  ["identity.api_token_scope", 403],
  ["identity.api_token_rate_limited", 429],
  ["request.invalid", 422],
  ["billing.plan_limit", 403],
] as const;
const GROUPS: (Scope | null)[] = [null, ...SCOPES.read, ...SCOPES.write];
const anchor = (scope: Scope | null) => `scope-${(scope ?? "none").replace(":", "-")}`;

/** The public API reference (public-api-docs spec, issue 334), built from the OpenAPI contract. */
export function ApiReference({ operations }: { operations: Operation[] }) {
  const t = useTranslations("apiDocs");
  const scopes = useTranslations("integrations");
  const label = (scope: Scope | null) => (scope ? scopes(`scopeShort.${scope}`) : t("noScope"));
  return <main id="content" tabIndex={-1} className="policy-page">
    <div className="policy-heading">
      <h1 className="page-title">{t("title")}</h1>
      <p>{t("intro")}</p>
      <p><Link href="/docs/mcp" className="underline">{t("mcpLink")}</Link></p>
    </div>
    <div className="policy-layout">
      <nav aria-label={t("index")} className="policy-index">
        <p className="font-medium">{t("index")}</p>
        <a href="#basics" className="underline">{t("basics.title")}</a>
        <a href="#errors" className="underline">{t("errors.title")}</a>
        {GROUPS.map((scope) => <a key={anchor(scope)} href={`#${anchor(scope)}`} className="underline">{label(scope)}</a>)}
      </nav>
      <div className="policy-copy">
        <section id="basics" aria-labelledby="basics-title">
          <h2 id="basics-title">{t("basics.title")}</h2>
          <p>{t("basics.key")}</p>
          <pre className="code-example"><code>Authorization: Bearer atesta_…</code></pre>
          <p>{t("basics.query")}</p>
          <p>{t("basics.limit")}</p>
          <p>{t("basics.language")}</p>
          <p>{t("basics.records")}</p>
        </section>
        <section id="errors" aria-labelledby="errors-title">
          <h2 id="errors-title">{t("errors.title")}</h2>
          <p>{t("errors.intro")}</p>
          <div className="table-region" role="region" aria-label={t("errors.title")} tabIndex={0}><table className="w-full text-left">
            <thead><tr><th scope="col">{t("errors.code")}</th><th scope="col">{t("errors.status")}</th><th scope="col">{t("errors.meaning")}</th></tr></thead>
            <tbody>{ERRORS.map(([code, status]) => <tr key={code}><td data-label={t("errors.code")} className="font-mono">{code}</td><td data-label={t("errors.status")} className="tabular-nums">{status}</td>
              <td data-label={t("errors.meaning")}>{t(`errors.codes.${code.replace(".", "_")}`)}</td></tr>)}</tbody>
          </table></div>
        </section>
        {GROUPS.map((scope) => <section key={anchor(scope)} id={anchor(scope)} aria-labelledby={`${anchor(scope)}-title`}>
          <h2 id={`${anchor(scope)}-title`}>{label(scope)}</h2>
          <p>{scope ? <><code>{scope}</code> · {scopes(`scope.${scope}`)}</> : t("noScopeHelp")}</p>
          {operations.filter((op) => op.scope === scope).map((op) => <article key={op.id} aria-labelledby={`${op.id}-title`}>
            <h3 id={`${op.id}-title`} className="font-mono wrap-anywhere">{`${op.method} ${op.path}`}</h3>
            <p>{t(`operations.${op.id}`)}</p>
            {op.body.length ? <div className="table-region" role="region" aria-label={t("fieldsOf", { operation: `${op.method} ${op.path}` })} tabIndex={0}><table className="w-full text-left">
              <thead><tr><th scope="col">{t("field")}</th><th scope="col">{t("type")}</th><th scope="col">{t("required")}</th><th scope="col">{t("limits")}</th></tr></thead>
              <tbody>{op.body.map((f) => <tr key={f.name}><td data-label={t("field")} className="font-mono">{f.name}</td><td data-label={t("type")} className="font-mono">{f.type}</td>
                <td data-label={t("required")}>{f.required ? t("yes") : t("no")}</td><td data-label={t("limits")} className="tabular-nums">{f.limits.join(", ")}</td></tr>)}</tbody>
            </table></div> : null}
          </article>)}
        </section>)}
      </div>
    </div>
  </main>;
}
