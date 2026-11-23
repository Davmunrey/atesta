"use client";

import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { type Policy, sha256Of, useApprovePolicy, useCreatePolicy, usePolicies } from "@/lib/api/routines";
import { type Membership, orgHome } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { Empty, LoadError, Loading, PageHeader, Panel } from "./page-frame";
import { RecordSummary } from "./record-summary";
import { policySummary } from "@/lib/summaries";

/** Policies (recorded-routines spec): where each lives, its approved version and when it is due. */
export function PoliciesView({ org }: { org: Membership }) {
  const t = useTranslations("routines.policies");
  const list = usePolicies(org.organization_id);
  const admin = canReviewControls(org.role);
  const s = useTranslations("summary.policies");
  const format = useFormatter();
  const sum = list.data?.length ? policySummary(list.data, new Date().toISOString().slice(0, 10)) : null;
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")} />
    {sum ? <RecordSummary lead={s("lead", { attention: sum.overdue + sum.unapproved })} figures={[
      { label: s("total"), value: format.number(sum.total) }, { label: s("current"), value: format.number(sum.current) },
      { label: s("overdue"), value: format.number(sum.overdue), attention: sum.overdue > 0 },
      { label: s("unapproved"), value: format.number(sum.unapproved), attention: sum.unapproved > 0 }]} /> : null}
    <Panel title={t("list")}>
      {list.isPending ? <Loading label={t("loading")} /> : list.isError ? <LoadError error={list.error} onRetry={() => void list.refetch()} />
        : list.data.length === 0 ? <Empty>{t("empty")}</Empty>
        : <ul className="policy-list">{list.data.map((p) => <PolicyRow key={p.id} policy={p} orgId={org.organization_id} admin={admin} />)}</ul>}
    </Panel>
    {admin ? <CreatePolicy orgId={org.organization_id} /> : null}
  </div>;
}

function Status({ policy }: { policy: Policy }) {
  const t = useTranslations("routines.policies");
  const format = useFormatter();
  if (!policy.latest || !policy.next_review_on) return <span className="badge" data-severity="missing"><Icon name="missing" />{t("unapproved")}</span>;
  const due = new Date(`${policy.next_review_on}T00:00:00Z`);
  const date = format.dateTime(due, { dateStyle: "medium", timeZone: "UTC" });
  const today = new Date().toISOString().slice(0, 10);
  return policy.next_review_on < today
    ? <span className="badge" data-severity="overdue"><Icon name="overdue" />{t("reviewOverdue", { date })}</span>
    : <span className="badge" data-severity="done"><Icon name="done" />{t("reviewBy", { date })}</span>;
}

function PolicyRow({ policy, orgId, admin }: { policy: Policy; orgId: string; admin: boolean }) {
  const t = useTranslations("routines.policies");
  const format = useFormatter();
  const [open, setOpen] = useState(false);
  return <li>
    <div className="policy-row">
      <div className="min-w-0">
        <a href={policy.location_url} className="text-link underline" rel="noopener noreferrer" target="_blank">{policy.title}</a>
        <p className="text-sm text-muted">{policy.latest
          ? t("latest", { version: policy.latest.version, approver: policy.latest.approver_name, date: format.dateTime(new Date(`${policy.latest.approved_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) })
          : t("never")}{policy.latest?.sha256 ? <> · <span className="font-mono">{policy.latest.sha256.slice(0, 12)}…</span></> : null}</p>
      </div>
      <Status policy={policy} />
      {admin ? <button type="button" className="dashboard-button" aria-expanded={open} onClick={() => setOpen(!open)}>{t("approve")}</button> : null}
    </div>
    {open ? <ApproveForm policyId={policy.id} orgId={orgId} onDone={() => setOpen(false)} /> : null}
  </li>;
}

function ApproveForm({ policyId, orgId, onDone }: { policyId: string; orgId: string; onDone: () => void }) {
  const t = useTranslations("routines.policies");
  const approve = useApprovePolicy(orgId);
  const ids = { version: useId(), approver: useId(), date: useId(), file: useId(), help: useId() };
  const [hash, setHash] = useState<string | null>(null);
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    approve.mutate({ policyId, body: {
      version: String(data.get("version") ?? ""), approver_name: String(data.get("approver") ?? ""),
      approved_on: String(data.get("approved_on") ?? ""), sha256: hash,
    } }, { onSuccess: onDone });
  }
  return <form onSubmit={submit} className="routine-form">
    <span><label htmlFor={ids.version}>{t("version")}</label><input id={ids.version} name="version" required maxLength={50} /></span>
    <span><label htmlFor={ids.approver}>{t("approver")}</label><input id={ids.approver} name="approver" required maxLength={200} /></span>
    <span><label htmlFor={ids.date}>{t("approvedOn")}</label><input id={ids.date} name="approved_on" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} /></span>
    <span className="routine-form-wide"><label htmlFor={ids.file}>{t("file")}</label>
      <input id={ids.file} type="file" aria-describedby={ids.help} onChange={(e) => { const f = e.target.files?.[0]; if (f) void sha256Of(f).then(setHash); else setHash(null); }} />
      <span id={ids.help} className="text-sm text-muted">{hash ? t("hash", { hash: `${hash.slice(0, 16)}…` }) : t("fileHelp")}</span></span>
    <div className="form-actions"><button type="submit" className="button-primary" disabled={approve.isPending}>{t("record")}</button></div>
    {approve.isError ? <ErrorMessage error={approve.error} /> : null}
  </form>;
}

function CreatePolicy({ orgId }: { orgId: string }) {
  const t = useTranslations("routines.policies");
  const create = useCreatePolicy(orgId);
  const ids = { title: useId(), url: useId(), months: useId() };
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    create.mutate({ title: String(data.get("title") ?? ""), location_url: String(data.get("location_url") ?? ""), review_months: Number(data.get("review_months") ?? 12) },
      { onSuccess: () => form.reset() });
  }
  return <Panel title={t("create")} description={t("createHelp")}>
    <form onSubmit={submit} className="routine-form">
      <span><label htmlFor={ids.title}>{t("policyTitle")}</label><input id={ids.title} name="title" required maxLength={200} /></span>
      <span><label htmlFor={ids.url}>{t("location")}</label><input id={ids.url} name="location_url" type="url" required pattern="https://.+" maxLength={2000} /></span>
      <span><label htmlFor={ids.months}>{t("reviewMonths")}</label><input id={ids.months} name="review_months" type="number" min={1} max={36} defaultValue={12} required /></span>
      <div className="form-actions"><button type="submit" className="button-primary" disabled={create.isPending}>{t("add")}</button></div>
      {create.isError ? <ErrorMessage error={create.error} /> : null}
    </form>
  </Panel>;
}
