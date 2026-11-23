"use client";

import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { type ApiToken, curlExample, useApiTokens, useCreateApiToken, useRevokeApiToken } from "@/lib/api/tokens";
import { evidenceTemplate, type TemplateFormat, USE_CASES, type UseCase } from "@/lib/evidence-templates";
import { type Membership, orgHome } from "@/lib/org";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { PageHeader, Panel } from "./page-frame";

const EXPIRIES = [30, 90, 180, 365] as const;

/** Integrations (evidence-ingestion-api spec): write-only tokens for the organization's tools. */
export function IntegrationsView({ org }: { org: Membership }) {
  const t = useTranslations("integrations");
  const list = useApiTokens(org.organization_id);
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")} />
    <CreateToken orgId={org.organization_id} />
    <Templates />
    <Panel title={t("list")}>
      {list.isPending ? <p role="status">{t("loading")}</p> : list.isError ? <ErrorMessage error={list.error} />
        : list.data.length === 0 ? <p className="text-muted">{t("empty")}</p>
        : <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("name")}</th><th scope="col">{t("lastUsed")}</th><th scope="col">{t("state")}</th><th scope="col"><span className="sr-only">{t("actions")}</span></th></tr></thead>
          <tbody>{list.data.map((token) => <TokenRow key={token.id} token={token} orgId={org.organization_id} />)}</tbody>
        </table></div>}
    </Panel>
  </div>;
}

function TokenRow({ token, orgId }: { token: ApiToken; orgId: string }) {
  const t = useTranslations("integrations");
  const format = useFormatter();
  const revoke = useRevokeApiToken(orgId);
  const day = (value: string) => format.dateTime(new Date(value), { dateStyle: "medium" });
  const expired = new Date(token.expires_at).getTime() <= new Date().getTime();
  return <tr>
    <td>{token.name}<span className="block text-sm text-muted"><span className="font-mono">{token.prefix}…</span> · {t("createdBy", { email: token.created_by_email, date: day(token.created_at) })}</span></td>
    <td className="tabular-nums">{token.last_used_at ? format.dateTime(new Date(token.last_used_at), { dateStyle: "medium", timeStyle: "short" }) : <span className="text-muted">{t("never")}</span>}</td>
    <td>{token.revoked_at ? <span className="badge" data-severity="missing"><Icon name="missing" />{t("revokedOn", { date: day(token.revoked_at) })}</span>
      : expired ? <span className="badge" data-severity="overdue"><Icon name="overdue" />{t("expiredOn", { date: day(token.expires_at) })}</span>
      : <span className="badge" data-severity="done"><Icon name="done" />{t("activeUntil", { date: day(token.expires_at) })}</span>}</td>
    <td>{token.revoked_at ? null : <button type="button" className="dashboard-button" disabled={revoke.isPending}
      aria-label={t("revokeNamed", { name: token.name })} onClick={() => revoke.mutate(token.id)}>{t("revoke")}</button>}
      {revoke.isError ? <ErrorMessage error={revoke.error} /> : null}</td>
  </tr>;
}

function CreateToken({ orgId }: { orgId: string }) {
  const t = useTranslations("integrations");
  const create = useCreateApiToken(orgId);
  const ids = { name: useId(), expiry: useId(), token: useId(), example: useId() };
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    create.mutate({ name: String(data.get("name") ?? ""), expires_in_days: Number(data.get("expires_in_days") ?? 90) },
      { onSuccess: (created) => { form.reset(); setCopied(false); setToken(created.token); } });
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
