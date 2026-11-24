"use client";

import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import {
  type Connection, ONBOARDING, useConnection, useConnections, useCreateConnection, useDisconnect, useScanNow, useStartSignIn, useVerify,
} from "@/lib/api/connections";
import { ApiError } from "@/lib/api/hooks";
import { type Membership, orgHome } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import type { State } from "@/lib/severity";
import { Badge } from "./badge";
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

/** Microsoft 365 connections (web-connections spec, issue 365): connect, verify, scan, disconnect. */
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
  const [open, setOpen] = useState(false);
  // Consented but not yet verified: the next step is Verificar, not connecting.
  const status = c.status === "pending_setup" && c.consented ? "pending_verification" : c.status;
  return <><tr aria-current={current ? "true" : undefined}>
    <td data-label={t("connection")}><span className="font-medium">{c.display_name}</span>
      <span className="block text-sm text-muted">{d(`providers.${c.provider as "m365" | "google_workspace"}`)}</span></td>
    <td data-label={t("tenant")}>{c.tenant_id ? <span className="font-mono text-sm">{c.tenant_id}</span> : <span className="text-muted">{t("noTenant")}</span>}</td>
    <td data-label={t("state")}><Badge state={STATE[c.status] ?? "connectionWaiting"}>{t(`statuses.${status as "active"}`)}</Badge>
      {c.status === "verifying" ? <span className="block text-sm text-muted">{t("verifyingNote")}</span> : null}</td>
    <td data-label={t("lastVerified")} className="tabular-nums">{c.verified_at ? format.dateTime(new Date(c.verified_at), { dateStyle: "medium", timeStyle: "short" }) : <span className="text-muted">{t("never")}</span>}</td>
    {admin ? <td data-label={t("actions")}><Actions connection={c} orgId={org.organization_id} navigate={navigate} /></td> : null}
  </tr>
  {/* The shared disclosure (DESIGN.md): fetched on first open, in a full-width row of its own. */}
  <tr className="row-detail"><td colSpan={admin ? 5 : 4} data-label={t("permissions")}>
    <details className="row-section" onToggle={(e) => { if (e.currentTarget.open) setOpen(true); }}>
      <summary>{t("permissions")}</summary>
      {open ? <Permissions orgId={org.organization_id} connection={c} /> : null}
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
  const onboarding = c.provider === "m365" && ONBOARDING.has(c.status);
  const failed = [signIn, verify, scan, disconnect].find((m) => m.isError);
  const connect = (label: string, primary: boolean) => <button type="button" className={primary ? "button-primary" : "dashboard-button"} disabled={signIn.isPending}
    aria-label={label} onClick={() => signIn.mutate(c.id, { onSuccess: (url) => navigate(url) })}>{primary ? t("connect") : t("reconnect")}</button>;
  if (confirming) { // the members pattern (DESIGN.md, Buttons): question, danger action, Cancelar
    return <span className="confirm-row">
      <span>{t("confirmDisconnect", { name })}</span>
      <button type="button" className="button-danger" disabled={disconnect.isPending}
        onClick={() => disconnect.mutate(c.id, { onSettled: () => setConfirming(false) })}>{t("confirm")}</button>
      <button type="button" className="dashboard-button" onClick={() => setConfirming(false)}>{t("cancel")}</button>
    </span>;
  }
  return <>
    <span className="flex flex-wrap items-center gap-2">
      {onboarding && !c.consented ? connect(t("connectNamed", { name }), true) : null}
      {onboarding && c.consented ? <>
        <button type="button" className="button-primary" disabled={verify.isPending} aria-label={t("verifyNamed", { name })} onClick={() => verify.mutate(c.id)}>{t("verify")}</button>
        {connect(t("reconnectNamed", { name }), false)}
      </> : null}
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
  const nameId = useId();
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const name = String(new FormData(form).get("display_name") ?? "").trim();
    create.mutate({ provider: "m365", display_name: name || t("defaultName") }, { onSuccess: () => form.reset() });
  }
  return <Panel title={t("add")} description={t("addHelp")}>
    <form onSubmit={submit} className="routine-form">
      <span><label htmlFor={nameId}>{t("name")}</label><input id={nameId} name="display_name" maxLength={100} defaultValue={t("defaultName")} /></span>
      <div className="form-actions"><button type="submit" className="button-primary" disabled={create.isPending}>{t("addButton")}</button></div>
      {create.isError ? <ErrorMessage error={create.error} /> : null}
    </form>
    <ul className="provider-list">
      <li><span className="font-medium">{d("providers.google_workspace")}</span> <span className="tag">{t("soon")}</span></li>
    </ul>
  </Panel>;
}
