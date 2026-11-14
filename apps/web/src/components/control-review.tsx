"use client";

import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";
import { useMembers, useRecordReview } from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { ErrorMessage } from "./error-message";

type Review = components["schemas"]["ReviewOut"];
type Decision = Review["status"];
const DAY = 86_400_000;
const isoDay = (offsetDays: number) => new Date(Date.now() + offsetDays * DAY).toISOString().slice(0, 10);

/** Human review of one manual control (manual-control-review spec). The API decides who may record. */
export function ControlReview(props: { orgId: string; frameworkKey: string; controlKey: string; review: Review | null; canReview: boolean }) {
  const t = useTranslations("framework.review");
  const format = useFormatter();
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
    </> : <p className="text-muted">{t("none")}</p>}
    {saved ? <p role="status">{t("saved")}</p> : null}
    {props.canReview && !editing ? <button type="button" className="dashboard-button" onClick={() => { setEditing(true); setSaved(false); }}>{t(review ? "update" : "record")}</button> : null}
    {props.canReview && editing ? <ReviewForm {...props} onDone={(ok) => { setEditing(false); setSaved(ok); }} /> : null}
  </div>;
}

function ReviewForm({ orgId, frameworkKey, controlKey, onDone }: { orgId: string; frameworkKey: string; controlKey: string; onDone: (saved: boolean) => void }) {
  const t = useTranslations("framework.review");
  const id = useId();
  const record = useRecordReview(orgId, frameworkKey);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [rationale, setRationale] = useState("");
  const [until, setUntil] = useState(isoDay(365));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!decision) return;
    record.mutate({ controlKey, status: decision, rationale: rationale.trim(), valid_until: until }, { onSuccess: () => onDone(true) });
  };
  return <form className="control-review-form" onSubmit={submit}>
    <fieldset><legend>{t("decision")}</legend>
      {(["pass", "fail"] as const).map((value) => <label key={value} className="control-review-choice">
        <input type="radio" name={`${id}-decision`} value={value} required checked={decision === value} onChange={() => setDecision(value)} /> {t(`status.${value}`)}
      </label>)}
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
