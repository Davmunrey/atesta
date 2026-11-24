"use client";

import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import {
  type Connection, ONBOARDING, useConnection, useConnections, useCreateConnection, useDisconnect, useScanNow, useSetGoogleSubject, useStartSignIn, useVerify,
} from "@/lib/api/connections";
import { ApiError } from "@/lib/api/hooks";
import { type Membership, orgHome } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import type { State } from "@/lib/severity";
import { Badge } from "./badge";
import { CopyButton } from "./copy-button";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { Empty, LoadError, Loading, PageHeader, Panel } from "./page-frame";

/** Each status as a shared severity state (DESIGN.md, severity mapping; issue 397). */
const STATE: Record<string, State> = {
  active: "connectionActive",
  verifying: "connectionWaiting",
  pending_setup: "connectionWaiting",
  pending_provisioning: "connectionWaiting",
  incomplete: "connectionIncomplete",
  over_privileged: "connectionOverPrivileged",
  revoked: "connectionRevoked",
};
type Provider = "m365" | "google_workspace";
const PROVIDERS: Provider[] = ["m365", "google_workspace"];
const isGoogle = (c: Connection) => c.provider === "google_workspace";
// Google: the super admin can be named while Atesta still provisions the accounts (issue 425).
const NAMING: ReadonlySet<string> = new Set([...ONBOARDING, "pending_provisioning"]);
/** Ready for Verificar: M365 once signed in and consented, Google once the super admin is named. */
const ready = (c: Connection) => ONBOARDING.has(c.status) && (isGoogle(c) ? c.google_subject_set : c.consented);

/** Microsoft 365 and Google Workspace connections (web-connections spec, issues 365 and 425). */
export function ConnectionsView({ org, focus = null, error = null, navigate = (url: string) => window.location.assign(url) }: {
  org: Membership; focus?: string | null; error?: string | null; navigate?: (url: string) => void;
}) {
  const t = useTranslations("connections");
  const list = useConnections(org.organization_id);
  const admin = canReviewControls(org.role);
  const shown = list.data?.filter((c) => c.status !== "disconnected") ?? [];
  const focused = shown.find((c) => c.id === focus) ?? null;
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")} />
    {error !== null ? <ErrorMessage error={new ApiError(400, error)} />
      : focused?.consented && ONBOARDING.has(focused.status) ? <p className="notice" role="status"><Icon name="done" />{t("consented", { name: focused.display_name })}</p> : null}
    <Panel title={t("list")}>
      {list.isPending ? <Loading label={t("loading")} /> : list.isError ? <LoadError error={list.error} onRetry={() => void list.refetch()} />
        : shown.length === 0 ? <Empty>{t("empty")}</Empty>
        : <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="connections-table w-full text-left">
          <thead><tr><th scope="col">{t("connection")}</th><th scope="col">{t("tenant")}</th><th scope="col">{t("state")}</th><th scope="col">{t("lastVerified")}</th>
            {admin ? <th scope="col"><span className="sr-only">{t("actions")}</span></th> : null}</tr></thead>
          <tbody>{shown.map((c) => <Row key={c.id} connection={c} org={org} admin={admin} current={c.id === focus} navigate={navigate} />)}</tbody>
        </table></div>}
      <Announcer connections={shown} />
    </Panel>
    {admin ? <Add orgId={org.organization_id} /> : null}
  </div>;
}

function Row({ connection: c, org, admin, current, navigate }: { connection: Connection; org: Membership; admin: boolean; current: boolean; navigate: (url: string) => void }) {
  const t = useTranslations("connections");
  const d = useTranslations("dashboard");
  const format = useFormatter();
  const google = isGoogle(c);
  // Google onboarding opens its steps for admins: they are the next thing to do.
  const [expanded, setExpanded] = useState(admin && google && NAMING.has(c.status));
  const [fetched, setFetched] = useState(expanded);
  // Ready but not yet verified: the next step is Verificar.
  const status = c.status === "pending_setup" && ready(c) ? "pending_verification" : c.status;
  const account = c.tenant_id ?? (google ? c.primary_domain : null); // Google pins its customer id at the first ok
  const note = c.status === "verifying" ? t(google ? "googleVerifyingNote" : "verifyingNote")
    : google && c.status === "pending_provisioning" ? t("googlePreparingNote")
    : google && c.status === "pending_setup" && !c.google_subject_set ? t("googleNextSubject") : null;
  return <><tr aria-current={current ? "true" : undefined}>
    <td data-label={t("connection")}><span className="font-medium">{c.display_name}</span>
      <span className="block text-sm text-muted">{d(`providers.${c.provider as Provider}`)}</span></td>
    <td data-label={t("tenant")}>{account ? <span className="font-mono text-sm">{account}</span> : <span className="text-muted">{t(google ? "noDomain" : "noTenant")}</span>}</td>
    <td data-label={t("state")}><Badge state={STATE[c.status] ?? "connectionWaiting"}>{t(`statuses.${status as "active"}`)}</Badge>
      {note ? <span className="block text-sm text-muted">{note}</span> : null}</td>
    <td data-label={t("lastVerified")} className="tabular-nums">{c.verified_at ? format.dateTime(new Date(c.verified_at), { dateStyle: "medium", timeStyle: "short" }) : <span className="text-muted">{t("never")}</span>}</td>
    {admin ? <td data-label={t("actions")}><Actions connection={c} orgId={org.organization_id} navigate={navigate} /></td> : null}
  </tr>
  {/* The shared disclosure (DESIGN.md): fetched on first open, in a full-width row of its own. */}
  <tr className="row-detail"><td colSpan={admin ? 5 : 4} data-label={t(google ? "googleAccess" : "permissions")}>
    <details className="row-section" open={expanded} onToggle={(e) => { const open = e.currentTarget.open; setExpanded(open); if (open) setFetched(true); }}>
      <summary>{t(google ? "googleAccess" : "permissions")}</summary>
      {!fetched ? null : google ? <GoogleAccess orgId={org.organization_id} connection={c} admin={admin} /> : <Permissions orgId={org.organization_id} connection={c} />}
    </details>
  </td></tr>
  </>;
}

function Actions({ connection: c, orgId, navigate }: { connection: Connection; orgId: string; navigate: (url: string) => void }) {
  const t = useTranslations("connections");
  const signIn = useStartSignIn(orgId);
  const verify = useVerify(orgId);
  const scan = useScanNow(orgId);
  const disconnect = useDisconnect(orgId);
  const [confirming, setConfirming] = useState(false);
  const name = c.display_name;
  const onboarding = !isGoogle(c) && ONBOARDING.has(c.status); // Microsoft's sign-in and consent
  const failed = [signIn, verify, scan, disconnect].find((m) => m.isError);
  const connect = (label: string, primary: boolean) => <button type="button" className={primary ? "button-primary" : "dashboard-button"} disabled={signIn.isPending}
    aria-label={label} onClick={() => signIn.mutate(c.id, { onSuccess: (url) => navigate(url) })}>{primary ? t("connect") : t("reconnect")}</button>;
  if (confirming) { // the members pattern (DESIGN.md, Buttons): question, danger action, Cancelar
    return <span className="confirm-row">
      <span>{t(isGoogle(c) ? "confirmDisconnectGoogle" : "confirmDisconnect", { name })}</span>
      <button type="button" className="button-danger" disabled={disconnect.isPending}
        onClick={() => disconnect.mutate(c.id, { onSettled: () => setConfirming(false) })}>{t("confirm")}</button>
      <button type="button" className="dashboard-button" onClick={() => setConfirming(false)}>{t("cancel")}</button>
    </span>;
  }
  return <>
    <span className="flex flex-wrap items-center gap-2">
      {onboarding && !c.consented ? connect(t("connectNamed", { name }), true) : null}
      {ready(c) ? <button type="button" className="button-primary" disabled={verify.isPending} aria-label={t("verifyNamed", { name })} onClick={() => verify.mutate(c.id)}>{t("verify")}</button> : null}
      {onboarding && c.consented ? connect(t("reconnectNamed", { name }), false) : null}
      {c.status === "active" ? <button type="button" className="button-primary" disabled={scan.isPending} aria-label={t("scanNamed", { name })} onClick={() => scan.mutate(c.id)}>{t("scan")}</button> : null}
      <button type="button" className="dashboard-button" aria-label={t("disconnectNamed", { name })} onClick={() => setConfirming(true)}>{t("disconnect")}</button>
    </span>
    {scan.isSuccess ? <p className="text-sm text-muted" role="status">{t("scanQueued")}</p> : null}
    {failed ? <ErrorMessage error={failed.error} /> : null}
  </>;
}

/** What the customer grants: the allowlist the verifier compares against, never typed here. */
function Permissions({ orgId, connection: c }: { orgId: string; connection: Connection }) {
  const t = useTranslations("connections");
  const detail = useConnection(orgId, c.id, true);
  const last = detail.data?.last_verification;
  if (detail.isPending) return <Loading label={t("loading")} />;
  if (detail.isError) return <LoadError error={detail.error} onRetry={() => void detail.refetch()} />;
  return <div className="permission-detail">
    <p className="text-sm">{t("permissionsLead", { count: detail.data.expected_access.permissions.length })}</p>
    <ul className="permission-list">{detail.data.expected_access.permissions.map((p) => <li key={p}>{p}</li>)}</ul>
    {last && last.missing.length > 0 ? <><p className="text-sm font-medium">{t("missing")}</p>
      <ul className="permission-list">{last.missing.map((p) => <li key={p}>{p}</li>)}</ul></> : null}
    {last && last.extra.length > 0 ? <><p className="text-sm font-medium">{t("extra")}</p>
      <ul className="permission-list">{last.extra.map((p) => <li key={p}>{p}</li>)}</ul></> : null}
  </div>;
}

/** Google onboarding (scanner-connectors spec, steps 2 and 3): the two delegation entries to add,
 *  then the super admin Atesta reads as. Ids and scopes come from the API; the web types none. */
function GoogleAccess({ orgId, connection: c, admin }: { orgId: string; connection: Connection; admin: boolean }) {
  const t = useTranslations("connections");
  const detail = useConnection(orgId, c.id, true);
  if (detail.isPending) return <Loading label={t("loading")} />;
  if (detail.isError) return <LoadError error={detail.error} onRetry={() => void detail.refetch()} />;
  const { google_client_id: scanId, google_verifier_client_id: verifierId, expected_access: access, last_verification: last } = detail.data;
  const clients = scanId && verifierId ? [
    { title: t("googleScanClient"), id: scanId, scopes: access.scan_scopes.join(","), copyId: t("copyScanId"), copyScopes: t("copyScanScopes") },
    { title: t("googleVerifierClient"), id: verifierId, scopes: access.verifier_scopes.join(","), copyId: t("copyVerifierId"), copyScopes: t("copyVerifierScopes") },
  ] : null;
  const naming = NAMING.has(c.status);
  return <div className="permission-detail">
    <ol className="setup-steps">
      <li><p className="font-medium">{t("googleStepAuthorize")}</p>
        {clients ? <>
          <p className="text-sm">{t("googlePath")}</p>
          {clients.map((client) => <div key={client.id} className="delegation-entry">
            <p className="text-sm font-medium">{client.title}</p>
            <dl>
              <dt>{t("clientId")}</dt><dd><span className="font-mono text-sm">{client.id}</span><CopyButton text={client.id} label={client.copyId} /></dd>
              <dt>{t("scopes")}</dt><dd><span className="font-mono text-sm">{client.scopes}</span><CopyButton text={client.scopes} label={client.copyScopes} /></dd>
            </dl>
          </div>)}
          <p className="text-sm text-muted">{t("googleMultiParty")}</p>
        </> : <p className="text-sm text-muted">{t("googlePreparing")}</p>}
      </li>
      {naming || c.google_subject_set ? <li><p className="font-medium">{t("googleStepSubject")}</p>
        {c.google_subject_set && c.primary_domain ? <p className="text-sm">{t("subjectSet", { domain: c.primary_domain })}</p> : null}
        {admin && naming ? <SubjectForm orgId={orgId} connectionId={c.id} /> : null}
      </li> : null}
      {naming ? <li><p className="text-sm">{t("googleStepVerify")}</p></li> : null}
    </ol>
    {last && last.missing.length > 0 ? <><p className="text-sm font-medium">{t("googleMissing")}</p>
      <ul className="permission-list">{last.missing.map((p) => <li key={p}>{p}</li>)}</ul></> : null}
    {last && last.extra.length > 0 ? <><p className="text-sm font-medium">{t("googleExtra")}</p>
      <ul className="permission-list">{last.extra.map((p) => <li key={p}>{p}</li>)}</ul></> : null}
  </div>;
}

/** The super admin's email; the primary domain only for an admin on a secondary domain (owner,
 *  2026-11-24). The API never sends the email back, so the form starts empty each time. */
function SubjectForm({ orgId, connectionId }: { orgId: string; connectionId: string }) {
  const t = useTranslations("connections");
  const save = useSetGoogleSubject(orgId);
  const [secondary, setSecondary] = useState(false);
  const ids = { email: useId(), help: useId(), secondary: useId(), domain: useId() };
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const email = String(data.get("email") ?? "").trim();
    const domain = String(data.get("primary_domain") ?? "").trim();
    save.mutate({ id: connectionId, email, ...(secondary && domain ? { primary_domain: domain } : {}) },
      { onSuccess: () => { form.reset(); setSecondary(false); } });
  }
  return <form onSubmit={submit} className="routine-form">
    <p id={ids.help} className="routine-form-wide text-sm text-muted">{t("googleSubjectHelp")}</p>
    <span><label htmlFor={ids.email}>{t("subjectEmail")}</label>
      <input id={ids.email} name="email" type="email" required maxLength={254} autoComplete="off" spellCheck={false} aria-describedby={ids.help} /></span>
    <span className="routine-form-wide checkbox-row"><input id={ids.secondary} type="checkbox" checked={secondary} onChange={(e) => setSecondary(e.target.checked)} />
      <label htmlFor={ids.secondary}>{t("secondaryDomain")}</label></span>
    {secondary ? <span><label htmlFor={ids.domain}>{t("primaryDomain")}</label>
      <input id={ids.domain} name="primary_domain" required maxLength={253} autoComplete="off" spellCheck={false} /></span> : null}
    <div className="form-actions"><button type="submit" className="button-primary" disabled={save.isPending}>{t("saveSubject")}</button></div>
    {save.isError ? <ErrorMessage error={save.error} /> : null}
  </form>;
}

/** Says, politely, when a verification ends; the table itself updates silently. */
function Announcer({ connections }: { connections: Connection[] }) {
  const t = useTranslations("connections");
  const seen = useRef(new Map<string, string>());
  const [message, setMessage] = useState("");
  useEffect(() => {
    for (const c of connections) {
      const before = seen.current.get(c.id);
      if (before === "verifying" && c.status !== "verifying") setMessage(t("statusChanged", { name: c.display_name, status: t(`statuses.${c.status as "active"}`) }));
      seen.current.set(c.id, c.status);
    }
  }, [connections, t]);
  return <p className="sr-only" role="status" aria-live="polite">{message}</p>;
}

function Add({ orgId }: { orgId: string }) {
  const t = useTranslations("connections");
  const d = useTranslations("dashboard");
  const create = useCreateConnection(orgId);
  const ids = { provider: useId(), name: useId() };
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const provider = data.get("provider") === "google_workspace" ? "google_workspace" : "m365";
    const name = String(data.get("display_name") ?? "").trim();
    create.mutate({ provider, display_name: name || d(`providers.${provider}`) }, { onSuccess: () => form.reset() });
  }
  return <Panel title={t("add")} description={t("addHelp")}>
    <form onSubmit={submit} className="routine-form">
      <span><label htmlFor={ids.provider}>{t("provider")}</label>
        <select id={ids.provider} name="provider" defaultValue="m365">{PROVIDERS.map((p) => <option key={p} value={p}>{d(`providers.${p}`)}</option>)}</select></span>
      <span><label htmlFor={ids.name}>{t("name")}</label><input id={ids.name} name="display_name" maxLength={100} /></span>
      <div className="form-actions"><button type="submit" className="button-primary" disabled={create.isPending}>{t("addButton")}</button></div>
      {create.isError ? <ErrorMessage error={create.error} /> : null}
    </form>
  </Panel>;
}
