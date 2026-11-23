"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { type TrainingCampaign, useCreateTraining, useTrainingCampaigns } from "@/lib/api/routines";
import { type Membership, orgHome, orgTrainingCampaign } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import { ErrorMessage } from "./error-message";
import { Icon } from "./icons";
import { PageHeader, Panel } from "./page-frame";
import { RecordSummary } from "./record-summary";
import { trainingSummary } from "@/lib/summaries";

const utcDay = (day: string) => new Date(`${day}T00:00:00Z`);

/** Training acknowledgements (recorded-routines spec): a shared link, confirmations, evidence. */
export function TrainingView({ org }: { org: Membership }) {
  const t = useTranslations("routines.training");
  const list = useTrainingCampaigns(org.organization_id);
  const s = useTranslations("summary.training");
  const format = useFormatter();
  const sum = list.data?.length ? trainingSummary(list.data) : null;
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }]} title={t("title")} description={t("intro")} />
    {sum ? <RecordSummary lead={s("lead", { open: sum.open, acknowledged: sum.acknowledged })} figures={[
      { label: s("total"), value: format.number(sum.total) }, { label: s("open"), value: format.number(sum.open) },
      { label: s("acknowledged"), value: format.number(sum.acknowledged) }]} /> : null}
    <Panel title={t("list")}>
      {list.isPending ? <p role="status">{t("loading")}</p> : list.isError ? <ErrorMessage error={list.error} />
        : list.data.length === 0 ? <p className="text-muted">{t("empty")}</p>
        : <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="w-full text-left">
          <thead><tr><th scope="col">{t("campaign")}</th><th scope="col">{t("people")}</th><th scope="col">{t("state")}</th></tr></thead>
          <tbody>{list.data.map((c) => <tr key={c.id}>
            <td data-label={t("campaign")}><Link href={orgTrainingCampaign(org.organization_id, c.id)} className="text-link underline">{c.title}</Link></td>
            <td data-label={t("people")} className="tabular-nums">{t("count", { count: c.acknowledged })}</td>
            <td data-label={t("state")}><CampaignState campaign={c} /></td>
          </tr>)}</tbody>
        </table></div>}
    </Panel>
    {canReviewControls(org.role) ? <CreateCampaign orgId={org.organization_id} /> : null}
  </div>;
}

export function CampaignState({ campaign }: { campaign: TrainingCampaign }) {
  const t = useTranslations("routines.training");
  const format = useFormatter();
  const day = (value: string) => format.dateTime(utcDay(value), { dateStyle: "medium", timeZone: "UTC" });
  if (campaign.closed_at) {
    return <span className="badge" data-severity="done"><Icon name="done" />{t("closedOn", { date: format.dateTime(new Date(campaign.closed_at), { dateStyle: "medium" }) })}</span>;
  }
  const ended = campaign.closes_on < new Date().toISOString().slice(0, 10);
  return ended
    ? <span className="badge" data-severity="overdue"><Icon name="overdue" />{t("ended", { date: day(campaign.closes_on) })}</span>
    : <span className="badge" data-severity="pending"><Icon name="pending" />{t("closesOn", { date: day(campaign.closes_on) })}</span>;
}

function CreateCampaign({ orgId }: { orgId: string }) {
  const t = useTranslations("routines.training");
  const create = useCreateTraining(orgId);
  const ids = { title: useId(), url: useId(), closes: useId(), link: useId() };
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    create.mutate({
      title: String(data.get("title") ?? ""), material_url: String(data.get("material_url") ?? ""),
      closes_on: String(data.get("closes_on") ?? ""),
    }, { onSuccess: (created) => { form.reset(); setCopied(false); setLink(created.link); } });
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
      <span><label htmlFor={ids.title}>{t("campaignTitle")}</label><input id={ids.title} name="title" required maxLength={200} /></span>
      <span><label htmlFor={ids.url}>{t("material")}</label><input id={ids.url} name="material_url" type="url" required pattern="https://.+" maxLength={2000} /></span>
      <span><label htmlFor={ids.closes}>{t("closes")}</label><input id={ids.closes} name="closes_on" type="date" required min={new Date().toISOString().slice(0, 10)} /></span>
      <div className="form-actions"><button type="submit" className="button-primary" disabled={create.isPending}>{t("add")}</button></div>
      {create.isError ? <ErrorMessage error={create.error} /> : null}
    </form>
    {link ? <div className="notice link-once" role="status">
      <p><strong>{t("linkTitle")}</strong> · {t("linkHelp")}</p>
      <span className="link-once-row">
        <label htmlFor={ids.link} className="sr-only">{t("linkLabel")}</label>
        <input id={ids.link} readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
        <button type="button" className="dashboard-button" onClick={() => void copy(link)}>{copied ? t("copied") : t("copy")}</button>
      </span>
    </div> : null}
  </Panel>;
}
