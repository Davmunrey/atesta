"use client";

import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useId, useRef, useState } from "react";
import { useControlEvidence } from "@/lib/api/evidence-hooks";
import { useMembers, useRecordReview } from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { ErrorMessage } from "./error-message";

type Review = components["schemas"]["ReviewOut"];
type Decision = Review["status"];
const DAY = 86_400_000;
const isoDay = (offsetDays: number) => new Date(Date.now() + offsetDays * DAY).toISOString().slice(0, 10);

/** Human review of one manual control (manual-control-review spec). The API decides who may record.
 *  A pass cites at least one evidence item of the control (issue 262); the API checks that too. */
export function ControlReview(props: { orgId: string; frameworkKey: string; controlKey: string; review: Review | null; canReview: boolean }) {
  const t = useTranslations("framework.review");
  const format = useFormatter();
  const citedId = useId();
  const members = useMembers(props.orgId);
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);
  const { review } = props;
  const author = members.data?.find((m) => m.user_id === review?.reviewed_by)?.email ?? t("someone");
  const day = (value: string) => format.dateTime(new Date(`${value.slice(0, 10)}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" });
  return <div className="control-review">
    <h5>{t("title")}</h5>
    {review ? <>
      <p><span className="requirement-state" data-state={review.expired ? "manual" : review.status}>{review.expired ? t("expired") : t(`status.${review.status}`)}</span>{" "}
        {t("summary", { author, date: day(review.reviewed_at), until: day(review.valid_until) })}</p>
      <p className="control-review-rationale">{review.rationale}</p>
      {review.evidence.length ? <>
        <p id={citedId} className="control-review-cited-label">{t("cited")}</p>
        <ul aria-labelledby={citedId} className="control-review-cited">
          {review.evidence.map((item) => <li key={item.id}>{item.title} <span className="text-muted">· {day(item.collected_at)}</span></li>)}
        </ul>
      </> : <p className="text-muted">{t("citesNone")}</p>}
    </> : <p className="text-muted">{t("none")}</p>}
    {saved ? <p role="status">{t("saved")}</p> : null}
    {props.canReview && !editing ? <button type="button" className="dashboard-button" onClick={() => { setEditing(true); setSaved(false); }}>{t(review ? "update" : "record")}</button> : null}
    {props.canReview && editing ? <ReviewForm {...props} onDone={(ok) => { setEditing(false); setSaved(ok); }} /> : null}
  </div>;
}

function ReviewForm({ orgId, frameworkKey, controlKey, onDone }: { orgId: string; frameworkKey: string; controlKey: string; onDone: (saved: boolean) => void }) {
  const t = useTranslations("framework.review");
  const format = useFormatter();
  const id = useId();
  const record = useRecordReview(orgId, frameworkKey);
  const evidence = useControlEvidence(orgId, controlKey, 0);
  const firstItem = useRef<HTMLInputElement>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [cited, setCited] = useState<ReadonlySet<string>>(new Set());
  const [missingEvidence, setMissingEvidence] = useState(false);
  const [rationale, setRationale] = useState("");
  const [until, setUntil] = useState(isoDay(365));
  const items = evidence.data?.items ?? [];
  const canPass = items.length > 0;
  const toggle = (itemId: string) => {
    const next = new Set(cited);
    if (!next.delete(itemId)) next.add(itemId);
    setCited(next);
    if (next.size > 0) setMissingEvidence(false);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!decision) return;
    if (decision === "pass" && cited.size === 0) {
      setMissingEvidence(true);
      firstItem.current?.focus();
      return;
    }
    const evidence_ids = items.filter((item) => cited.has(item.id)).map((item) => item.id);
    record.mutate({ controlKey, status: decision, rationale: rationale.trim(), valid_until: until, evidence_ids }, { onSuccess: () => onDone(true) });
  };
  const describedBy = [`${id}-evidence-help`, missingEvidence ? `${id}-evidence-error` : null].filter(Boolean).join(" ");
  return <form className="control-review-form" onSubmit={submit}>
    <fieldset><legend>{t("decision")}</legend>
      {(["pass", "fail"] as const).map((value) => <label key={value} className="control-review-choice">
        <input type="radio" name={`${id}-decision`} value={value} required checked={decision === value} disabled={value === "pass" && !canPass}
          onChange={() => setDecision(value)} /> {t(`status.${value}`)}
      </label>)}
    </fieldset>
    <fieldset className="control-review-evidence" aria-describedby={describedBy}>
      <legend>{t("evidence")}</legend>
      <p id={`${id}-evidence-help`} className="text-sm text-muted">{evidence.isPending ? t("evidenceLoading") : canPass ? t("evidenceHelp") : t("evidenceNone")}</p>
      {evidence.isError ? <ErrorMessage error={evidence.error} /> : null}
      {items.map((item, index) => <label key={item.id} className="control-review-choice">
        <input ref={index === 0 ? firstItem : undefined} type="checkbox" name={`${id}-evidence`} value={item.id} checked={cited.has(item.id)} onChange={() => toggle(item.id)} />
        <span>{item.title} <span className="text-muted">· {format.dateTime(new Date(item.collected_at), { dateStyle: "medium" })}</span></span>
      </label>)}
      {evidence.data && evidence.data.total > items.length ? <p className="text-sm text-muted">{t("evidenceNewest", { count: items.length })}</p> : null}
      {missingEvidence ? <p id={`${id}-evidence-error`} role="alert" className="control-review-error">{t("evidenceRequired")}</p> : null}
    </fieldset>
    <label htmlFor={`${id}-rationale`}>{t("rationale")}</label>
    <p id={`${id}-rationale-help`} className="text-sm text-muted">{t("rationaleHelp")}</p>
    <textarea id={`${id}-rationale`} aria-describedby={`${id}-rationale-help`} required maxLength={2000} rows={4} value={rationale} onChange={(e) => setRationale(e.target.value)} />
    <label htmlFor={`${id}-until`}>{t("validUntil")}</label>
    <input id={`${id}-until`} type="date" required min={isoDay(1)} max={isoDay(3 * 365)} value={until} onChange={(e) => setUntil(e.target.value)} />
    <p className="text-sm text-muted">{t("scoreNote")}</p>
    {record.isError ? <ErrorMessage error={record.error} /> : null}
    <div className="control-review-actions">
      <button type="submit" className="dashboard-button" disabled={record.isPending}>{t(record.isPending ? "saving" : "save")}</button>
      <button type="button" className="dashboard-button" onClick={() => onDone(false)}>{t("cancel")}</button>
    </div>
  </form>;
}
