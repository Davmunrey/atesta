"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useId, useSyncExternalStore } from "react";
import type { Scope } from "@/lib/api/tokens";
import { CopyButton } from "./copy-button";

/** The MCP server's tools and the permission each needs; a test keeps it equal to server.py. */
export const MCP_TOOLS: { read: { name: string; scope: Scope | null }[]; write: { name: string; scope: Scope }[] } = {
  read: [
    { name: "get_key", scope: null },
    { name: "list_frameworks", scope: "compliance:read" },
    { name: "list_measures", scope: "compliance:read" },
    { name: "get_measure", scope: "compliance:read" },
    { name: "list_gaps", scope: "compliance:read" },
    { name: "list_due_items", scope: "compliance:read" },
    { name: "list_incidents", scope: "incidents:read" },
    { name: "get_incident", scope: "incidents:read" },
  ],
  write: [
    { name: "record_evidence", scope: "evidence:write" },
    { name: "propose_assessment", scope: "assessment:propose" },
    { name: "record_incident", scope: "routines:write" },
    { name: "add_incident_update", scope: "routines:write" },
    { name: "start_training_campaign", scope: "routines:write" },
    { name: "start_access_review", scope: "routines:write" },
  ],
};
const SECTIONS = ["what", "safety", "setup", "hosted", "tools"] as const;
const noChanges = () => () => {}; // the page's origin never changes while it is open
const LOCAL_SERVERS = "https://modelcontextprotocol.io/docs/develop/connect-local-servers";

/** How to connect an AI agent to Atesta over MCP (public-api-docs spec, issue 334). */
export function McpGuide() {
  const t = useTranslations("mcpGuide");
  const locale = useLocale();
  const configId = useId();
  const origin = useSyncExternalStore(noChanges, () => window.location.origin, () => "https://…");
  const config = JSON.stringify({ mcpServers: { atesta: { command: "atesta-mcp", env: {
    ATESTA_API_URL: origin, ATESTA_API_KEY: "atesta_…", ATESTA_LANGUAGE: locale } } } }, null, 2);
  return <main id="content" tabIndex={-1} className="policy-page">
    <div className="policy-heading">
      <h1 className="page-title">{t("title")}</h1>
      <p>{t("intro")}</p>
      <p><Link href="/docs/api" className="underline">{t("apiLink")}</Link></p>
    </div>
    <div className="policy-layout">
      <nav aria-label={t("index")} className="policy-index">
        <p className="font-medium">{t("index")}</p>
        {SECTIONS.map((id) => <a key={id} href={`#${id}`}>{t(`${id}.title`)}</a>)}
      </nav>
      <div className="policy-copy">
        <section id="what" aria-labelledby="what-title">
          <h2 id="what-title">{t("what.title")}</h2>
          <p>{t("what.body")}</p>
        </section>
        <section id="safety" aria-labelledby="safety-title">
          <h2 id="safety-title">{t("safety.title")}</h2>
          <ul>{(["scopes", "proposals", "data", "systems"] as const).map((k) => <li key={k}>{t(`safety.${k}`)}</li>)}</ul>
        </section>
        <section id="setup" aria-labelledby="setup-title">
          <h2 id="setup-title">{t("setup.title")}</h2>
          <ol>
            <li>{t.rich("setup.key", { link: (chunks) => <Link href="/app/integrations" className="underline">{chunks}</Link> })}</li>
            <li>{t("setup.install")}</li>
            <li>{t.rich("setup.config", { link: (chunks) => <a href={LOCAL_SERVERS} className="underline" rel="noopener">{chunks}</a> })}</li>
          </ol>
          <label htmlFor={configId} className="font-medium">{t("setup.configLabel")}</label>
          <textarea id={configId} readOnly rows={12} className="code-example" value={config} onFocus={(e) => e.currentTarget.select()} />
          <CopyButton text={config} label={t("setup.copy")} />
          <p className="text-sm text-muted">{t("setup.secret")}</p>
        </section>
        <section id="hosted" aria-labelledby="hosted-title">
          <h2 id="hosted-title">{t("hosted.title")}</h2>
          <p>{t("hosted.body")}</p>
        </section>
        <section id="tools" aria-labelledby="tools-title">
          <h2 id="tools-title">{t("tools.title")}</h2>
          {(["read", "write"] as const).map((group) => <div key={group} className="table-region" role="region" aria-label={t(`tools.${group}`)} tabIndex={0}>
            <table className="w-full text-left">
              <caption className="text-left font-medium">{t(`tools.${group}`)}</caption>
              <thead><tr><th scope="col">{t("tools.name")}</th><th scope="col">{t("tools.does")}</th><th scope="col">{t("tools.scope")}</th></tr></thead>
              <tbody>{MCP_TOOLS[group].map((tool) => <tr key={tool.name}><td data-label={t("tools.name")} className="font-mono">{tool.name}</td>
                <td data-label={t("tools.does")}>{t(`tools.list.${tool.name}`)}</td><td data-label={t("tools.scope")} className="font-mono">{tool.scope ?? "—"}</td></tr>)}</tbody>
            </table>
          </div>)}
        </section>
      </div>
    </div>
  </main>;
}
