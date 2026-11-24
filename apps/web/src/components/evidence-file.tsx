"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { useDownloadEvidenceFile, useUploadEvidenceFile } from "@/lib/api/evidence-hooks";
import { ApiError } from "@/lib/api/hooks";
import type { components } from "@/lib/api/schema";
import { fileSize } from "@/lib/format";
import type { State } from "@/lib/severity";
import { Badge } from "./badge";
import { ErrorMessage } from "./error-message";

type StoredFile = components["schemas"]["FileOut"];
type Limits = components["schemas"]["FileUploads"];
type Context = { orgId: string; controlKey: string };

/** The malware scan, as the panel shows it (evidence-malware-scanning spec). The API decides what
 *  it serves; the button is offered only where it would. */
const SCAN: Record<StoredFile["scan_status"], { label: string; state: State; help?: string; served: boolean }> = {
  pending: { label: "pending", state: "fileScanPending", help: "pending", served: false },
  threats_found: { label: "blocked", state: "fileBlocked", help: "blocked", served: false },
  unsupported: { label: "failed", state: "fileNotScanned", help: "failed", served: false },
  access_denied: { label: "failed", state: "fileNotScanned", help: "failed", served: false },
  failed: { label: "failed", state: "fileNotScanned", help: "failed", served: false },
  not_scanned: { label: "devUnscanned", state: "fileDevUnscanned", served: true },
  no_threats_found: { label: "clean", state: "fileClean", served: true },
};

/** Shown in this order; "jpeg" is the same type as "jpg" and is not listed twice. */
const SHOWN = ["pdf", "png", "jpg", "txt", "csv", "docx", "xlsx"];
const extension = (name: string) => (name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : "");
const stem = (name: string) => (name.includes(".") ? name.slice(0, name.lastIndexOf(".")) : name);

/** What the API would refuse, said before anything is sent. The API still decides. */
function refusal(file: File, limits: Limits): ApiError | null {
  if (!limits.extensions.includes(extension(file.name)) || !stem(file.name).trim()) return new ApiError(415, "evidence.file_type_not_allowed");
  if (file.size === 0) return new ApiError(422, "evidence.file_empty");
  if (file.size > limits.max_bytes) return new ApiError(413, "evidence.file_too_large");
  return null;
}

/** Upload one file as evidence of a control (evidence-file-uploads spec). */
export function EvidenceFileForm({ orgId, controlKey, limits, onDone }: Context & { limits: Limits; onDone: (saved: boolean) => void }) {
  const t = useTranslations("evidence");
  const format = useFormatter();
  const locale = useLocale();
  const id = useId();
  const mutation = useUploadEvidenceFile(orgId, controlKey);
  // One submission id per file and title, so a retry after an uncertain failure is the same upload.
  const attempt = useRef<{ file: File; title: string; id: string } | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => { fileInput.current?.focus(); }, []);
  const refused = file ? refusal(file, limits) : null;
  const ready = file !== null && refused === null && title.trim() !== "";
  const types = format.list(SHOWN.filter((e) => limits.extensions.includes(e)).map((e) => e.toUpperCase()), { type: "disjunction" });
  const choose = (chosen: File | null) => {
    setFile(chosen);
    if (chosen && !title.trim()) setTitle(stem(chosen.name).slice(0, 200));
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    const name = title.trim();
    if (attempt.current?.file !== file || attempt.current.title !== name) attempt.current = { file, title: name, id: crypto.randomUUID() };
    mutation.mutate({ submissionId: attempt.current.id, title: name, file }, { onSuccess: () => onDone(true) });
  };
  return <form className="evidence-form" onSubmit={submit}>
    <fieldset disabled={mutation.isPending}>
      <legend>{t("upload")}</legend>
      <label htmlFor={`${id}-file`}>{t("file")}</label>
      <input ref={fileInput} id={`${id}-file`} type="file" aria-required="true" accept={limits.extensions.map((e) => `.${e}`).join(",")} aria-describedby={`${id}-file-help`} onChange={(e) => choose(e.target.files?.[0] ?? null)} />
      <p id={`${id}-file-help`} className="text-sm text-muted">{t("fileHelp", { types, size: fileSize(locale, limits.max_bytes) })}</p>
      {refused ? <ErrorMessage error={refused} /> : null}
      <label htmlFor={`${id}-title`}>{t("title")}</label>
      <input id={`${id}-title`} required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} />
      <p className="text-sm text-muted">{t("scanned")}</p>
      <p className="text-sm text-muted">{t("immutable")}</p>
      {mutation.isError ? <ErrorMessage error={mutation.error} /> : null}
      <div className="evidence-actions">
        <button className="dashboard-button" type="submit" disabled={!ready}>{t(mutation.isPending ? "uploading" : "upload")}</button>
        <button className="dashboard-button" type="button" onClick={() => onDone(false)}>{t("cancel")}</button>
      </div>
    </fieldset>
  </form>;
}

/** Name, type, size and scan status of an uploaded file, with a download that the API verifies
 *  first, offered only once the file is known clean. */
export function EvidenceFileLine({ orgId, evidenceId, file }: { orgId: string; evidenceId: string; file: StoredFile }) {
  const t = useTranslations("evidence");
  const locale = useLocale();
  const download = useDownloadEvidenceFile(orgId);
  const save = (data: Blob) => {
    const url = URL.createObjectURL(data);
    const link = Object.assign(document.createElement("a"), { href: url, download: file.name });
    link.click();
    URL.revokeObjectURL(url);
  };
  const scan = SCAN[file.scan_status];
  return <div className="evidence-file">
    <p><span className="evidence-file-name">{file.name}</span> <span className="evidence-metadata">{t("fileDetails", { type: extension(file.name).toUpperCase(), size: fileSize(locale, file.size_bytes) })}</span></p>
    <Badge state={scan.state}>{t(`scan.${scan.label}`)}</Badge>
    {scan.served ? <button type="button" className="dashboard-button" aria-label={t("downloadFile", { name: file.name })} disabled={download.isPending} onClick={() => download.mutate(evidenceId, { onSuccess: save })}>{t(download.isPending ? "downloading" : "download")}</button> : null}
    {scan.help ? <p className="evidence-scan-help text-sm text-muted">{t(`scanHelp.${scan.help}`)}</p> : null}
    {download.isError ? <ErrorMessage error={download.error} /> : null}
  </div>;
}
