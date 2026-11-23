"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { parseAccounts, useAccessReviews, useCreateAccessReview } from "@/lib/api/routines";
import { type Membership, orgAccessReview, orgHome } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { PageHeader, Panel } from "./page-frame";
import { RecordSummary } from "./record-summary";
import { reviewSummary } from "@/lib/summaries";

/** Access reviews (recorded-routines spec): who keeps access, decided and recorded per account. */
export function AccessReviewsView({ org }: { org: Membership }) {
  const t = useTranslations("routines.access");
  const format = useFormatter();
  const list = useAccessReviews(org.organization_id);
  const admin = canReviewControls(org.role);
  const s = useTranslations("summary.access");
  const sum = list.data?.length ? reviewSummary(list.data, new Date().toISOString().slice(0, 10)) : null;
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")} />
    {sum ? <RecordSummary lead={s("lead", { open: sum.open, pending: sum.pending })} figures={[
      { label: s("total"), value: format.number(sum.total) }, { label: s("open"), value: format.number(sum.open), attention: sum.late > 0 },
      { label: s("closed"), value: format.number(sum.closed) }, { label: s("pending"), value: format.number(sum.pending) }]} /> : null}
    <Panel title={t("list")}>
      {list.isPending ? <p role="status">{t("loading")}</p> : list.isError ? <ErrorMessage error={list.error} />
        : list.data.length === 0 ? <p className="text-muted">{t("empty")}</p>
        : <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("review")}</th><th scope="col">{t("progress")}</th><th scope="col">{t("state")}</th></tr></thead>
          <tbody>{list.data.map((r) => <tr key={r.id}>
            <td data-label={t("review")}><Link href={orgAccessReview(org.organization_id, r.id)} className="text-link underline">{r.title}</Link>
              <span className="block text-sm text-muted">{r.system}</span></td>
            <td data-label={t("progress")} className="tabular-nums">{t("decided", { decided: r.total - r.pending, total: r.total })}</td>
            <td data-label={t("state")}>{r.closed_at ? <span className="badge" data-severity="done"><Icon name="done" />{t("closedOn", { date: format.dateTime(new Date(r.closed_at), { dateStyle: "medium" }) })}</span>
              : r.due_on ? <span className="badge" data-severity="pending"><Icon name="pending" />{t("dueOn", { date: format.dateTime(new Date(`${r.due_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) })}</span>
              : <span className="badge" data-severity="pending"><Icon name="pending" />{t("open")}</span>}</td>
          </tr>)}</tbody>
        </table></div>}
    </Panel>
    {admin ? <CreateReview org={org} /> : null}
  </div>;
}

function CreateReview({ org }: { org: Membership }) {
  const t = useTranslations("routines.access");
  const create = useCreateAccessReview(org.organization_id);
  const ids = { title: useId(), system: useId(), due: useId(), accounts: useId(), file: useId(), help: useId() };
  const [text, setText] = useState("");
  const accounts = parseAccounts(text);
  async function readFile(file: File | undefined) { if (file) setText(await file.text()); }
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    create.mutate({
      title: String(data.get("title") ?? ""), system: String(data.get("system") ?? ""),
      due_on: String(data.get("due_on") ?? "") || null, accounts,
    }, { onSuccess: () => setText("") });
  }
  return <Panel title={t("create")} description={t("createHelp")}>
    <form onSubmit={submit} className="routine-form">
      <span><label htmlFor={ids.title}>{t("reviewTitle")}</label><input id={ids.title} name="title" required maxLength={200} /></span>
      <span><label htmlFor={ids.system}>{t("system")}</label><input id={ids.system} name="system" required maxLength={200} /></span>
      <span><label htmlFor={ids.due}>{t("due")}</label><input id={ids.due} name="due_on" type="date" /></span>
      <span className="routine-form-wide">
        <label htmlFor={ids.accounts}>{t("accounts")}</label>
        <textarea id={ids.accounts} rows={6} value={text} onChange={(e) => setText(e.target.value)} aria-describedby={ids.help} />
        <span id={ids.help} className="text-sm text-muted">{t("accountsHelp", { count: accounts.length })}</span>
      </span>
      <span className="routine-form-wide"><label htmlFor={ids.file}>{t("csv")}</label>
        <input id={ids.file} type="file" accept=".csv,.txt,text/csv,text/plain" onChange={(e) => void readFile(e.target.files?.[0])} /></span>
      <div className="form-actions"><button type="submit" className="button-primary" disabled={create.isPending || accounts.length === 0}>{t("start")}</button></div>
      {create.isError ? <ErrorMessage error={create.error} /> : null}
    </form>
  </Panel>;
}
