"use client";

import { useFormatter, useTranslations } from "next-intl";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { EVIDENCE_PAGE_SIZE, useControlEvidence, useRecordEvidence } from "@/lib/api/evidence-hooks";
import { useMembers } from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { CatalogReference } from "./catalog-reference";
import { ErrorMessage } from "@atesta/ui/error-message";
import { EvidenceFileForm, EvidenceFileLine } from "./evidence-file";
import { Empty, LoadError, Loading } from "@atesta/ui/page-frame";

type Context = { orgId: string; controlKey: string };
type FileUploads = components["schemas"]["FileUploads"];

export function ControlEvidence(props: Context) {
  const t = useTranslations("evidence");
  const id = useId();
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  return <div className="control-evidence">
    <button type="button" className="evidence-toggle" aria-expanded={open} aria-controls={id} onClick={() => { setOpen(!open); setLoaded(true); }}>{t(open ? "hide" : "show")}</button>
    <div id={id} hidden={!open}>{loaded ? <EvidenceWorkspace {...props} active={open} /> : null}</div>
  </div>;
}

function EvidenceWorkspace({ orgId, controlKey, active }: Context & { active: boolean }) {
  const t = useTranslations("evidence");
  const format = useFormatter();
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<"statement" | "file" | null>(null);
  const [saved, setSaved] = useState<"statement" | "file" | null>(null);
  const recordButton = useRef<HTMLButtonElement>(null);
  const uploadButton = useRef<HTMLButtonElement>(null);
  const wasEditing = useRef<"statement" | "file" | null>(null);
  useEffect(() => {  // back to the button that opened the form
    if (!editing && wasEditing.current && active) (wasEditing.current === "file" ? uploadButton : recordButton).current?.focus();
    wasEditing.current = editing;
  }, [editing, active]);
  const query = useControlEvidence(orgId, controlKey, offset, active);
  const results = useRef<HTMLDivElement>(null);
  const changingPage = useRef(false);
  const changePage = (next: number) => { changingPage.current = true; setOffset(next); };
  useEffect(() => {
    if (changingPage.current && !query.isFetching && active) {
      results.current?.focus();
      changingPage.current = false;
    }
  }, [query.isFetching, offset, active]);
  const members = useMembers(orgId);
  // Offered only where the API says uploads work (evidence-file-uploads spec); kept across refetches.
  const uploads = (query.data as { file_uploads?: FileUploads } | undefined)?.file_uploads;
  return <div className="evidence-workspace">
    <p className="text-sm text-muted">{t("boundary")}</p>
    {saved ? <p role="status">{t(saved === "file" ? "uploaded" : "saved")}</p> : null}
    <div ref={results} tabIndex={-1} role="region" aria-label={t("pages")} aria-busy={query.isFetching}>
    {query.isPending ? <Loading label={t("loading")} /> : query.isError ? <LoadError error={query.error} onRetry={() => void query.refetch()} />
    : query.data ? <>
      <p className="evidence-count">{t("count", { count: query.data.total })}</p>
      {query.data.total === 0 ? <Empty>{t("empty")}</Empty> : <ol className="evidence-list">
        {query.data.items.map((item) => <li key={item.id}>
          <strong>{item.title}</strong>
          <p className="evidence-metadata">{t("recorded", { author: members.data?.find((m) => m.user_id === item.created_by)?.email ?? t(item.kind === "scan_output" ? "scanner" : "member"), date: format.dateTime(new Date(item.created_at), { dateStyle: "medium", timeStyle: "short" }) })}</p>
          {item.file ? <EvidenceFileLine orgId={orgId} evidenceId={item.id} file={item.file} /> : <p className="evidence-statement">{item.statement ?? t("collected")}</p>}
          {item.reference_url ? <p className="evidence-reference"><CatalogReference value={item.reference_url} /></p> : null}
        </li>)}
      </ol>}
      {query.data.total > EVIDENCE_PAGE_SIZE ? <nav className="evidence-actions" aria-label={t("pages")}>
        <button type="button" className="dashboard-button" disabled={offset === 0} onClick={() => changePage(offset - EVIDENCE_PAGE_SIZE)}>{t("previous")}</button>
        <span>{t("page", { page: Math.floor(offset / EVIDENCE_PAGE_SIZE) + 1, pages: Math.ceil(query.data.total / EVIDENCE_PAGE_SIZE) })}</span>
        <button type="button" className="dashboard-button" disabled={offset + EVIDENCE_PAGE_SIZE >= query.data.total} onClick={() => changePage(offset + EVIDENCE_PAGE_SIZE)}>{t("next")}</button>
      </nav> : null}
    </> : null}
    </div>
    {editing === "statement" ? <EvidenceForm orgId={orgId} controlKey={controlKey} onDone={(ok) => { setEditing(null); setSaved(ok ? "statement" : null); if (ok) setOffset(0); }} />
      : editing === "file" && uploads ? <EvidenceFileForm orgId={orgId} controlKey={controlKey} limits={uploads} onDone={(ok) => { setEditing(null); setSaved(ok ? "file" : null); if (ok) setOffset(0); }} />
      : <div className="evidence-actions">
        <button ref={recordButton} type="button" className="dashboard-button" onClick={() => { setEditing("statement"); setSaved(null); }}>{t("record")}</button>
        {uploads?.enabled ? <button ref={uploadButton} type="button" className="dashboard-button" onClick={() => { setEditing("file"); setSaved(null); }}>{t("upload")}</button> : null}
      </div>}
  </div>;
}

function EvidenceForm({ orgId, controlKey, onDone }: Context & { onDone: (saved: boolean) => void }) {
  const t = useTranslations("evidence");
  const id = useId();
  const mutation = useRecordEvidence(orgId, controlKey);
  const attempt = useRef<{ payload: string; id: string } | null>(null);
  const [title, setTitle] = useState("");
  const [statement, setStatement] = useState("");
  const [reference, setReference] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);
  useEffect(() => { titleInput.current?.focus(); }, []);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!title.trim() || !statement.trim()) return;
    const body = { title: title.trim(), statement: statement.trim(), reference_url: reference.trim() || null };
    const payload = JSON.stringify(body);
    if (attempt.current?.payload !== payload) attempt.current = { payload, id: crypto.randomUUID() };
    mutation.mutate({ ...body, submission_id: attempt.current.id }, { onSuccess: () => onDone(true) });
  };
  return <form className="evidence-form" onSubmit={submit}>
    <fieldset disabled={mutation.isPending}>
      <legend>{t("record")}</legend>
      <label htmlFor={`${id}-title`}>{t("title")}</label>
      <input ref={titleInput} id={`${id}-title`} required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
      <label htmlFor={`${id}-statement`}>{t("statement")}</label>
      <textarea id={`${id}-statement`} required maxLength={10000} rows={5} value={statement} onChange={(e) => setStatement(e.target.value)} />
      <label htmlFor={`${id}-reference`}>{t("reference")}</label>
      <input id={`${id}-reference`} type="url" pattern="https://.*" maxLength={2048} aria-describedby={`${id}-reference-help`} value={reference} onChange={(e) => setReference(e.target.value)} />
      <p id={`${id}-reference-help`} className="text-sm text-muted">{t("referenceHelp")}</p>
      <p className="text-sm text-muted">{t("immutable")}</p>
      {mutation.isError ? <ErrorMessage error={mutation.error} /> : null}
      <div className="evidence-actions">
        <button className="dashboard-button" type="submit" disabled={!title.trim() || !statement.trim()}>{t(mutation.isPending ? "saving" : "save")}</button>
        <button className="dashboard-button" type="button" onClick={() => onDone(false)}>{t("cancel")}</button>
      </div>
    </fieldset>
  </form>;
}
