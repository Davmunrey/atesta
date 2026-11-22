"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useId, useState, type FormEvent } from "react";
import { useMembers } from "@/lib/api/hooks";
import {
  applicabilityUrl, isOverdue, registerProgress, useRecordAssessment, useRecordAssessmentReview, useRecordAssignment,
  useRecordScope, type AssessmentInput, type AxisValues, type Register, type RegisterItem,
} from "@/lib/api/register-hooks";
import { ErrorMessage } from "./error-message";

type Ctx = { orgId: string; frameworkKey: string; canEdit: boolean };

/** Scope, progress, reviewer sign-off and export for one framework (requirement-register spec). */
export function SelfAssessmentPanel({ register, ...ctx }: Ctx & { register: Register }) {
  const t = useTranslations("register");
  const locale = useLocale();
  const progress = registerProgress(register.items);
  return <section aria-labelledby="self-assessment-heading" className="self-assessment">
    <h2 id="self-assessment-heading">{t("title")}</h2>
    <p className="text-muted">{t("intro")}</p>
    <ol className="assessment-steps">
      <li data-done={register.scope ? "true" : "false"}><ScopeStep register={register} {...ctx} /></li>
      <li data-done={progress.assessed === progress.total && progress.total > 0 ? "true" : "false"}>
        <h3>{t("stepAssess")}</h3>
        <p>{t("progress", { assessed: progress.assessed, total: progress.total })}</p>
        <progress max={progress.total} value={progress.assessed} aria-label={t("progressLabel")} />
        <p className="text-sm text-muted">{t("breakdown", { applies: progress.applies, implemented: progress.implemented, partial: progress.partial, notApplicable: progress.notApplicable })}</p>
      </li>
      <li data-done={register.review ? "true" : "false"}><ReviewStep register={register} {...ctx} /></li>
      <li data-done="false">
        <h3>{t("stepExport")}</h3>
        <p className="text-sm text-muted">{t("exportHelp")}</p>
        <p className="export-links">
          <a className="dashboard-button" href={applicabilityUrl(ctx.orgId, ctx.frameworkKey, "csv", locale)} download>{t("exportCsv")}</a>
          <a className="text-link underline" href={applicabilityUrl(ctx.orgId, ctx.frameworkKey, "json")} target="_blank" rel="noopener">{t("exportJson")}</a>
        </p>
      </li>
    </ol>
  </section>;
}

/** The pack's readable label for an official scope term; the bare term (Spanish) when it has none. */
function useTermLabel(register: Register) {
  const english = useLocale() === "en";
  const labels = new Map(register.term_labels.map((l) => [l.term, english ? l.en : l.es]));
  return (term: string) => ({ text: labels.get(term) ?? term, lang: labels.has(term) ? undefined : "es" });
}

function ScopeStep({ register, orgId, frameworkKey, canEdit }: Ctx & { register: Register }) {
  const t = useTranslations("register");
  const format = useFormatter();
  const term = useTermLabel(register);
  const save = useRecordScope(orgId, frameworkKey);
  const axes = Object.entries(register.axes).map(([axis, def]) => [axis, { keys: def.keys ?? [], levels: def.levels ?? [] }] as const);
  const current = (register.scope?.axis_values ?? {}) as Record<string, unknown>;
  const [editing, setEditing] = useState(!register.scope);
  const [values, setValues] = useState<Record<string, string | Record<string, string>>>(() => Object.fromEntries(axes.map(([axis, def]) => {
    const value = current[axis];
    if (def.keys.length === 0) return [axis, typeof value === "string" ? value : def.levels[0] ?? ""];
    const known = (value && typeof value === "object" ? value : {}) as Record<string, string>;
    return [axis, Object.fromEntries(def.keys.map((k) => [k, known[k] ?? def.levels[0] ?? ""]))];
  })));
  if (axes.length === 0) return <><h3>{t("stepScope")}</h3><p className="text-sm text-muted">{t("noAxes")}</p></>;
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(values as AxisValues, { onSuccess: () => setEditing(false) }); };
  const show = (value: unknown) => (typeof value === "string" ? term(value).text : "—");
  const summary = axes.map(([axis, def]) => def.keys.length === 0 ? `${term(axis).text}: ${show(current[axis])}`
    : `${term(axis).text}: ${def.keys.map((k) => `${term(k).text} ${show(((current[axis] ?? {}) as Record<string, string>)[k])}`).join(" · ")}`).join(" — ");
  return <>
    <h3>{t("stepScope")}</h3>
    {register.scope && !editing ? <>
      <p lang={register.term_labels.length ? undefined : "es"}>{summary}</p>
      <p className="text-sm text-muted">{t("scopeRecorded", { date: format.dateTime(new Date(register.scope.decided_at), { dateStyle: "medium" }) })}</p>
      {canEdit ? <button className="dashboard-button" onClick={() => setEditing(true)}>{t("changeScope")}</button> : null}
    </> : canEdit ? <form onSubmit={submit} className="scope-form">
      <p className="text-sm text-muted">{t("scopeHelp")}</p>
      {axes.map(([axis, def]) => def.keys.length === 0
        ? <AxisSelect key={axis} label={axis} term={term} levels={def.levels} value={values[axis] as string} onChange={(v) => setValues({ ...values, [axis]: v })} />
        : <fieldset key={axis}><legend lang={term(axis).lang}>{term(axis).text}</legend><div className="scope-dimensions">{def.keys.map((k) =>
          <AxisSelect key={k} label={k} term={term} levels={def.levels} value={(values[axis] as Record<string, string>)[k] ?? ""}
            onChange={(v) => setValues({ ...values, [axis]: { ...(values[axis] as Record<string, string>), [k]: v } })} />)}</div></fieldset>)}
      {save.isError ? <ErrorMessage error={save.error} /> : null}
      <div className="form-actions"><button type="submit" className="button-primary" disabled={save.isPending}>{t("saveScope")}</button>
        {register.scope ? <button type="button" className="dashboard-button" onClick={() => setEditing(false)}>{t("cancel")}</button> : null}</div>
    </form> : <p className="text-sm text-muted">{t("scopeMissingMember")}</p>}
  </>;
}

type TermLabel = (term: string) => { text: string; lang: string | undefined };

/** Shows readable labels; the value sent stays the pack's official term. */
function AxisSelect({ label, term, levels, value, onChange }: { label: string; term: TermLabel; levels: string[]; value: string; onChange: (v: string) => void }) {
  const id = useId();
  return <span className="axis-select"><label htmlFor={id} lang={term(label).lang}>{term(label).text}</label>
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>{levels.map((l) => <option key={l} value={l} lang={term(l).lang}>{term(l).text}</option>)}</select></span>;
}

function ReviewStep({ register, orgId, frameworkKey, canEdit }: Ctx & { register: Register }) {
  const t = useTranslations("register");
  const format = useFormatter();
  const save = useRecordAssessmentReview(orgId, frameworkKey);
  const [open, setOpen] = useState(false);
  const ids = { name: useId(), role: useId(), date: useId(), conclusions: useId(), actions: useId() };
  const [form, setForm] = useState({ reviewer_name: "", reviewer_role: "", reviewed_on: new Date().toISOString().slice(0, 10), conclusions: "", corrective_actions: "" });
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(form, { onSuccess: () => setOpen(false) }); };
  return <>
    <h3>{t("stepReview")}</h3>
    {register.review ? <p>{t("reviewRecorded", { name: register.review.reviewer_name, role: register.review.reviewer_role, date: format.dateTime(new Date(register.review.reviewed_on), { dateStyle: "medium" }) })}</p>
      : <p className="text-sm text-muted">{t("reviewHelp")}</p>}
    {canEdit && !open ? <button className="dashboard-button" onClick={() => setOpen(true)}>{register.review ? t("newReview") : t("recordReview")}</button> : null}
    {open ? <form onSubmit={submit} className="register-form">
      <label htmlFor={ids.name}>{t("reviewerName")}</label><input id={ids.name} required maxLength={200} value={form.reviewer_name} onChange={(e) => setForm({ ...form, reviewer_name: e.target.value })} />
      <label htmlFor={ids.role}>{t("reviewerRole")}</label><input id={ids.role} required maxLength={200} value={form.reviewer_role} onChange={(e) => setForm({ ...form, reviewer_role: e.target.value })} />
      <label htmlFor={ids.date}>{t("reviewedOn")}</label><input id={ids.date} type="date" required value={form.reviewed_on} onChange={(e) => setForm({ ...form, reviewed_on: e.target.value })} />
      <label htmlFor={ids.conclusions}>{t("conclusions")}</label><textarea id={ids.conclusions} required maxLength={4000} rows={4} value={form.conclusions} onChange={(e) => setForm({ ...form, conclusions: e.target.value })} />
      <label htmlFor={ids.actions}>{t("correctiveActions")}</label><textarea id={ids.actions} maxLength={4000} rows={3} value={form.corrective_actions} onChange={(e) => setForm({ ...form, corrective_actions: e.target.value })} />
      <p className="text-sm text-muted">{t("reviewNotAtesta")}</p>
      {save.isError ? <ErrorMessage error={save.error} /> : null}
      <div className="form-actions"><button type="submit" className="button-primary" disabled={save.isPending}>{t("saveReview")}</button>
        <button type="button" className="dashboard-button" onClick={() => setOpen(false)}>{t("cancel")}</button></div>
    </form> : null}
  </>;
}

/** What the register shows in a requirement row's summary: the person's decision, else the proposal. */
export function AssessmentBadge({ item }: { item: RegisterItem | undefined }) {
  const t = useTranslations("register");
  if (!item) return null;
  const overdue = isOverdue(item, new Date().toISOString().slice(0, 10));
  return <span className="assessment-badges">{overdue ? <span className="overdue-flag">{t("overdue")}</span> : null}<StateBadge item={item} /></span>;
}

function StateBadge({ item }: { item: RegisterItem }) {
  const t = useTranslations("register");
  if (item.assessment) {
    const state = item.assessment.applicability === "not_applicable" ? "not_applicable" : item.assessment.implementation;
    return <span className="requirement-state" data-assessment={state}>{t(`states.${state}`)}</span>;
  }
  return <span className="requirement-state" data-assessment="pending">{t("states.pending")}
    {item.proposal.decision !== "undecided" ? <span className="proposal-hint"> · {t(`proposal.${item.proposal.decision}`)}</span> : null}</span>;
}

/** The organization's own assessment of one requirement; the API decides who may write. */
export function AssessmentForm({ item, orgId, frameworkKey, canEdit, canAssess = canEdit }: Ctx & { item: RegisterItem; canAssess?: boolean }) {
  const t = useTranslations("register");
  const format = useFormatter();
  const save = useRecordAssessment(orgId, frameworkKey);
  const a = item.assessment;
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<AssessmentInput>({
    applicability: a?.applicability ?? (item.proposal.decision === "not_applicable" ? "not_applicable" : "applies"),
    implementation: a?.implementation ?? "not_implemented",
    regularly_reviewed: a?.regularly_reviewed ?? false,
    justification: a?.justification ?? "", performed_by: a?.performed_by ?? "",
    performed_on: a?.performed_on ?? null, evidence_statement_ids: a?.evidence_statement_ids ?? [], notes: a?.notes ?? "",
  });
  const ids = { impl: useId(), by: useId(), on: useId(), just: useId(), notes: useId(), rev: useId() };
  const differs = item.proposal.decision !== "undecided" && item.proposal.decision !== form.applicability;
  const needsJustification = form.applicability === "not_applicable" || differs;
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate({ code: item.code, body: form }, { onSuccess: () => setEditing(false) }); };
  const proposal = item.proposal.decision === "undecided" ? t("proposalUndecided")
    : t.rich("proposalText", { decision: t(`proposal.${item.proposal.decision}`), rule: item.proposal.rule ?? "", level: item.proposal.level ?? "",
      official: (chunks) => <span lang="es">{chunks}</span> });
  return <div className="assessment-card">
    <OwnerField item={item} orgId={orgId} frameworkKey={frameworkKey} canEdit={canEdit} />
    <h3>{t("yourAssessment")}</h3>
    <p className="text-sm text-muted">{proposal}</p>
    {a && !editing ? <>
      <dl className="assessment-summary">
        <div><dt>{t("applicability")}</dt><dd>{t(`proposal.${a.applicability}`)}</dd></div>
        {a.applicability === "applies" ? <div><dt>{t("implementation")}</dt><dd>{t(`states.${a.implementation}`)}{a.regularly_reviewed ? ` · ${t("regularlyReviewed")}` : ""}</dd></div> : null}
        {a.performed_by ? <div><dt>{t("performedBy")}</dt><dd>{a.performed_by}{a.performed_on ? ` · ${format.dateTime(new Date(a.performed_on), { dateStyle: "medium" })}` : ""}</dd></div> : null}
        {a.justification ? <div><dt>{t("justification")}</dt><dd>{a.justification}</dd></div> : null}
        {a.notes ? <div><dt>{t("notes")}</dt><dd>{a.notes}</dd></div> : null}
      </dl>
      <p className="text-sm text-muted">{t("recordedAt", { date: format.dateTime(new Date(a.recorded_at), { dateStyle: "medium", timeStyle: "short" }) })}</p>
      {canAssess ? <button className="dashboard-button" onClick={() => setEditing(true)}>{t("update")}</button> : null}
    </> : !canAssess ? <p className="text-sm text-muted">{t("pendingMember")}</p> : !editing && !a ? <button className="button-primary" onClick={() => setEditing(true)}>{t("assess")}</button>
      : <form onSubmit={submit} className="register-form">
        <fieldset><legend>{t("applicability")}</legend>
          {(["applies", "not_applicable"] as const).map((v) => <label key={v} className="radio"><input type="radio" name={`app-${item.code}`} checked={form.applicability === v} onChange={() => setForm({ ...form, applicability: v })} />{t(`proposal.${v}`)}</label>)}
        </fieldset>
        {form.applicability === "applies" ? <>
          <label htmlFor={ids.impl}>{t("implementation")}</label>
          <select id={ids.impl} value={form.implementation} onChange={(e) => setForm({ ...form, implementation: e.target.value as AssessmentInput["implementation"] })}>
            {(["not_implemented", "partially_implemented", "implemented"] as const).map((v) => <option key={v} value={v}>{t(`states.${v}`)}</option>)}
          </select>
          <label className="checkbox" htmlFor={ids.rev}><input id={ids.rev} type="checkbox" checked={form.regularly_reviewed} onChange={(e) => setForm({ ...form, regularly_reviewed: e.target.checked })} />{t("regularlyReviewedQuestion")}</label>
        </> : null}
        <label htmlFor={ids.just}>{t("justification")}{needsJustification ? ` (${t("required")})` : ""}</label>
        <textarea id={ids.just} rows={2} maxLength={2000} required={needsJustification} value={form.justification} onChange={(e) => setForm({ ...form, justification: e.target.value })} />
        {needsJustification ? <p className="text-sm text-muted">{t("justificationHelp")}</p> : null}
        <div className="form-row">
          <span><label htmlFor={ids.by}>{t("performedBy")}</label><input id={ids.by} maxLength={200} value={form.performed_by} onChange={(e) => setForm({ ...form, performed_by: e.target.value })} placeholder={t("performedByPlaceholder")} /></span>
          <span><label htmlFor={ids.on}>{t("performedOn")}</label><input id={ids.on} type="date" value={form.performed_on ?? ""} onChange={(e) => setForm({ ...form, performed_on: e.target.value || null })} /></span>
        </div>
        <label htmlFor={ids.notes}>{t("notes")}</label>
        <textarea id={ids.notes} rows={2} maxLength={2000} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        {save.isError ? <ErrorMessage error={save.error} /> : null}
        <div className="form-actions"><button type="submit" className="button-primary" disabled={save.isPending}>{t("save")}</button>
          <button type="button" className="dashboard-button" onClick={() => setEditing(false)}>{t("cancel")}</button></div>
      </form>}
  </div>;
}

/** Who owns the measure and by when (insights spec); the owner is a member, the API checks it. */
function OwnerField({ item, orgId, frameworkKey, canEdit }: Ctx & { item: RegisterItem }) {
  const t = useTranslations("register");
  const format = useFormatter();
  const members = useMembers(orgId);
  const save = useRecordAssignment(orgId, frameworkKey);
  const [editing, setEditing] = useState(false);
  const [owner, setOwner] = useState(item.assignment?.owner_user_id ?? "");
  const [due, setDue] = useState(item.assignment?.due_on ?? "");
  const ids = { owner: useId(), due: useId() };
  const email = (members.data ?? []).find((m) => m.user_id === item.assignment?.owner_user_id)?.email;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({ code: item.code, body: { owner_user_id: owner || null, due_on: due || null } }, { onSuccess: () => setEditing(false) });
  };
  const named = members.isSuccess ? email ?? t("formerMember") : t("assignedOwner"); // auditors see no names
  if (!editing) return <p className="owner-line text-sm">
    <span className="text-muted">{t("owner")}:</span> {item.assignment?.owner_user_id ? named : t("noOwner")}
    {item.assignment?.due_on ? <> · <span className="text-muted">{t("dueOn")}:</span> {format.dateTime(new Date(`${item.assignment.due_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" })}</> : null}
    {canEdit ? <> <button type="button" className="text-link underline owner-edit" onClick={() => setEditing(true)}>{t("changeOwner")}</button></> : null}
  </p>;
  return <form onSubmit={submit} className="register-form owner-form">
    <div className="form-row">
      <span><label htmlFor={ids.owner}>{t("owner")}</label>
        <select id={ids.owner} value={owner} onChange={(e) => setOwner(e.target.value)}>
          <option value="">{t("noOwner")}</option>
          {(members.data ?? []).map((m) => <option key={m.user_id} value={m.user_id}>{m.display_name ?? m.email}</option>)}
        </select></span>
      <span><label htmlFor={ids.due}>{t("dueOn")}</label><input id={ids.due} type="date" value={due} onChange={(e) => setDue(e.target.value)} /></span>
    </div>
    {save.isError ? <ErrorMessage error={save.error} /> : null}
    <div className="form-actions"><button type="submit" className="button-primary" disabled={save.isPending}>{t("saveOwner")}</button>
      <button type="button" className="dashboard-button" onClick={() => setEditing(false)}>{t("cancel")}</button></div>
  </form>;
}
