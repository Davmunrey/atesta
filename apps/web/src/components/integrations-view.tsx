"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { type ApiToken, curlExample, RATE_LIMITS, type Scope, SCOPES, useApiTokens, useApiTokenUsage, useCreateApiToken, useRevokeApiToken } from "@/lib/api/tokens";
import { evidenceTemplate, type TemplateFormat, USE_CASES, type UseCase } from "@/lib/evidence-templates";
import { type Membership, orgHome } from "@/lib/org";
import { Badge } from "@atesta/ui/badge";
import { ErrorMessage } from "@atesta/ui/error-message";
import { Icon } from "@atesta/ui/icons";
import { Empty, LoadError, Loading, PageHeader, Panel } from "@atesta/ui/page-frame";
import { RecordSummary, useRecordStates } from "./record-summary";

const EXPIRIES = [30, 90, 180, 365] as const;

/** Integrations (evidence-ingestion-api, api-keys-v2 specs): scoped keys for tools and agents. */
export function IntegrationsView({ org }: { org: Membership }) {
  const t = useTranslations("integrations");
  const list = useApiTokens(org.organization_id);
  const states = useRecordStates();
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")} />
    {list.data?.length ? <RecordSummary state={states.tokens(list.data)} /> : null}
    <p className="text-sm">{t.rich("docs", { api: (c) => <Link href="/docs/api" className="underline">{c}</Link>, mcp: (c) => <Link href="/docs/mcp" className="underline">{c}</Link> })}</p>
    <Panel title={t("list")}>
      {list.isPending ? <Loading label={t("loading")} /> : list.isError ? <LoadError error={list.error} onRetry={() => void list.refetch()} />
        : list.data.length === 0 ? <Empty>{t("empty")}</Empty>
        : <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("name")}</th><th scope="col">{t("lastUsed")}</th><th scope="col">{t("state")}</th><th scope="col"><span className="sr-only">{t("actions")}</span></th></tr></thead>
          <tbody>{list.data.map((token) => <TokenRow key={token.id} token={token} orgId={org.organization_id} />)}</tbody>
        </table></div>}
    </Panel>
    <CreateToken orgId={org.organization_id} />
    <Templates />
  </div>;
}

function TokenRow({ token, orgId }: { token: ApiToken; orgId: string }) {
  const t = useTranslations("integrations");
  const format = useFormatter();
  const revoke = useRevokeApiToken(orgId);
  const day = (value: string) => format.dateTime(new Date(value), { dateStyle: "medium" });
  const expired = new Date(token.expires_at).getTime() <= new Date().getTime();
  return <tr>
    <td data-label={t("name")}>{token.name}{token.read_only ? <span className="tag">{t("readOnly")}</span> : null}
      <span className="block text-sm text-muted"><span className="font-mono">{token.prefix}…</span> · {t("createdBy", { email: token.created_by_email, date: day(token.created_at) })}</span>
      <span className="block text-sm text-muted">{[...token.scopes.map((s) => t(`scopeShort.${s as Scope}`)), t("perMinute", { count: token.rate_limit_per_minute })].join(" · ")}</span>
      <Usage token={token} orgId={orgId} /></td>
    <td data-label={t("lastUsed")} className="tabular-nums">{token.last_used_at ? format.dateTime(new Date(token.last_used_at), { dateStyle: "medium", timeStyle: "short" }) : <span className="text-muted">{t("never")}</span>}</td>
    <td data-label={t("state")}>{token.revoked_at ? <Badge state="tokenRevoked">{t("revokedOn", { date: day(token.revoked_at) })}</Badge>
      : expired ? <Badge state="tokenExpired">{t("expiredOn", { date: day(token.expires_at) })}</Badge>
      : <Badge state="tokenActive">{t("activeUntil", { date: day(token.expires_at) })}</Badge>}</td>
    <td data-label={t("actions")}>{token.revoked_at ? null : <button type="button" className="dashboard-button" disabled={revoke.isPending}
      aria-label={t("revokeNamed", { name: token.name })} onClick={() => revoke.mutate(token.id)}>{t("revoke")}</button>}
      {revoke.isError ? <ErrorMessage error={revoke.error} /> : null}</td>
  </tr>;
}

/** The usage log of one key, fetched when the admin opens it (api-keys-v2 spec). */
function Usage({ token, orgId }: { token: ApiToken; orgId: string }) {
  const t = useTranslations("integrations");
  const format = useFormatter();
  const [open, setOpen] = useState(false);
  const usage = useApiTokenUsage(orgId, token.id, open);
  return <details className="technical-details" onToggle={(e) => setOpen(e.currentTarget.open)}>
    <summary>{t("usageOf", { name: token.name })}</summary>
    {!open ? null : usage.isPending ? <Loading label={t("loading")} /> : usage.isError ? <LoadError error={usage.error} onRetry={() => void usage.refetch()} />
      : <><p>{t("usageCount", { count: usage.data.last_24h })}</p>
        {usage.data.recent.length === 0 ? <p>{t("usageEmpty")}</p> : <ol className="text-sm">{usage.data.recent.map((r, i) =>
          <li key={i}><span className="tabular-nums">{format.dateTime(new Date(r.at), { dateStyle: "medium", timeStyle: "short" })}</span> · <span className="font-mono">{`${r.method} ${r.route}`}</span> · {r.scope ? t(`scopeShort.${r.scope as Scope}`) : t("noScope")}</li>)}</ol>}</>}
  </details>;
}

function CreateToken({ orgId }: { orgId: string }) {
  const t = useTranslations("integrations");
  const create = useCreateApiToken(orgId);
  const ids = { name: useId(), expiry: useId(), limit: useId(), token: useId(), example: useId(), scopesHelp: useId() };
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [scopes, setScopes] = useState<ReadonlySet<Scope>>(new Set());
  const [noScope, setNoScope] = useState(false);
  function toggle(scope: Scope) {
    const next = new Set(scopes);
    if (next.has(scope)) next.delete(scope); else next.add(scope);
    setScopes(next);
    setNoScope(false);
  }
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (scopes.size === 0) { setNoScope(true); return; }
    const form = e.currentTarget;
    const data = new FormData(form);
    const chosen = [...SCOPES.read, ...SCOPES.write].filter((s) => scopes.has(s));
    create.mutate({ name: String(data.get("name") ?? ""), expires_in_days: Number(data.get("expires_in_days") ?? 90), scopes: chosen, rate_limit_per_minute: Number(data.get("rate_limit_per_minute") ?? 60) },
      { onSuccess: (created) => { form.reset(); setScopes(new Set()); setCopied(false); setToken(created.token); } });
  }
  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false); // the field stays selectable for a manual copy
    }
  }
  return <Panel title={t("create")} description={t("createHelp")}>
    <form onSubmit={submit} className="routine-form">
      <span><label htmlFor={ids.name}>{t("name")}</label><input id={ids.name} name="name" required maxLength={100} placeholder={t("namePlaceholder")} /></span>
      <span><label htmlFor={ids.expiry}>{t("expiry")}</label>
        <select id={ids.expiry} name="expires_in_days" defaultValue={90}>{EXPIRIES.map((d) => <option key={d} value={d}>{t("days", { count: d })}</option>)}</select></span>
      <span><label htmlFor={ids.limit}>{t("rateLimit")}</label>
        <select id={ids.limit} name="rate_limit_per_minute" defaultValue={60}>{RATE_LIMITS.map((n) => <option key={n} value={n}>{t("perMinute", { count: n })}</option>)}</select></span>
      <fieldset className="routine-form-wide" aria-describedby={ids.scopesHelp}><legend>{t("scopes")}</legend>
        <p id={ids.scopesHelp} className="text-sm text-muted">{t("scopesHelp")}</p>
        {(["read", "write"] as const).map((group) => <fieldset key={group}><legend>{t(`scopeGroup.${group}`)}</legend>
          {SCOPES[group].map((scope) => <span key={scope} className="checkbox-row"><input id={`${ids.scopesHelp}-${scope}`} type="checkbox" checked={scopes.has(scope)} onChange={() => toggle(scope)} />
            <label htmlFor={`${ids.scopesHelp}-${scope}`}>{t(`scope.${scope}`)}</label></span>)}</fieldset>)}
        <button type="button" className="dashboard-button" onClick={() => { setScopes(new Set(SCOPES.read)); setNoScope(false); }}>{t("readOnlyPreset")}</button>
      </fieldset>
      {noScope ? <p role="alert" className="routine-form-wide rounded-md border border-danger px-3 py-2 text-danger"><Icon name="overdue" />{t("scopesRequired")}</p> : null}
      <div className="form-actions"><button type="submit" className="button-primary" disabled={create.isPending}>{t("add")}</button></div>
      {create.isError ? <ErrorMessage error={create.error} /> : null}
    </form>
    {token ? <div className="notice link-once" role="status">
      <p><strong>{t("tokenTitle")}</strong> · {t("tokenHelp")}</p>
      <span className="link-once-row">
        <label htmlFor={ids.token} className="sr-only">{t("tokenLabel")}</label>
        <input id={ids.token} readOnly value={token} onFocus={(e) => e.currentTarget.select()} />
        <button type="button" className="dashboard-button" onClick={() => void copy(token)}>{copied ? t("copied") : t("copy")}</button>
      </span>
      <label htmlFor={ids.example} className="text-sm">{t("example")}</label>
      <textarea id={ids.example} readOnly rows={5} className="code-example" value={curlExample(window.location.origin, token)} />
    </div> : null}
  </Panel>;
}

/** Ready-made scripts per use case and runner (evidence-ingestion-api spec, templates). */
function Templates() {
  const t = useTranslations("integrations.templates");
  const ids = { useCase: useId(), format: useId(), script: useId() };
  const [useCase, setUseCase] = useState<UseCase>("backup");
  const [format, setFormat] = useState<TemplateFormat>("powershell");
  const [copied, setCopied] = useState(false);
  const script = evidenceTemplate(useCase, format, window.location.origin, {
    title: t(`cases.${useCase}.title`), statement: t(`cases.${useCase}.statement`), when: t(`when.${useCase}`), secret: t("secret"),
  });
  async function copy() {
    try {
      await navigator.clipboard.writeText(script);
      setCopied(true);
    } catch {
      setCopied(false); // the text area stays selectable for a manual copy
    }
  }
  return <Panel title={t("title")} description={t("help")}>
    <div className="routine-form">
      <span><label htmlFor={ids.useCase}>{t("useCase")}</label>
        <select id={ids.useCase} value={useCase} onChange={(e) => { setUseCase(e.target.value as UseCase); setCopied(false); }}>
          {(Object.keys(USE_CASES) as UseCase[]).map((u) => <option key={u} value={u}>{t(`cases.${u}.label`)}</option>)}
        </select></span>
      <span><label htmlFor={ids.format}>{t("format")}</label>
        <select id={ids.format} value={format} onChange={(e) => { setFormat(e.target.value as TemplateFormat); setCopied(false); }}>
          {(["powershell", "bash", "github"] as const).map((f) => <option key={f} value={f}>{t(`formats.${f}`)}</option>)}
        </select></span>
      <span className="routine-form-wide"><label htmlFor={ids.script}>{t("script")}</label>
        <textarea id={ids.script} readOnly rows={14} className="code-example" value={script} onFocus={(e) => e.currentTarget.select()} /></span>
      <div className="form-actions"><button type="button" className="dashboard-button" onClick={() => void copy()}>{copied ? t("copied") : t("copy")}</button></div>
    </div>
  </Panel>;
}
