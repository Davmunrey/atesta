"use client";

import Link from "next/link";
import { orgDossier } from "@/lib/org";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { useId, useState, type FormEvent } from "react";
import { useMembers } from "@/lib/api/hooks";
import {
  applicabilityUrl, isOverdue, registerProgress, useDecideProposal, useRecordAssessment, useRecordAssessmentReview, useRecordAssignment,
  useRecordScope, type AssessmentInput, type AxisValues, type Register, type RegisterItem,
} from "@/lib/api/register-hooks";
import { ErrorMessage } from "./error-message";
import { useGuideReference } from "./expected-evidence";
import { AssessmentFields, AssessmentIntro, AssessmentState } from "./measure-sheet";
import { ScopeGuide } from "./scope-guide";
import { Icon } from "./icons";

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
          <Link className="button-primary" href={orgDossier(ctx.orgId, ctx.frameworkKey)}>{t("exportDossier")}</Link>
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
  const english = useLocale() === "en";
  const save = useRecordScope(orgId, frameworkKey);
  const axes = Object.entries(register.axes).map(([axis, def]) => [axis, { keys: def.keys ?? [], levels: def.levels ?? [] }] as const);
  const current = (register.scope?.axis_values ?? {}) as Record<string, unknown>;
  const [profile, setProfile] = useState(typeof current.profile === "string" ? current.profile : "");
  const [editing, setEditing] = useState(!register.scope);
  const [values, setValues] = useState<Record<string, string | Record<string, string>>>(() => Object.fromEntries(axes.map(([axis, def]) => {
    const value = current[axis];
    if (def.keys.length === 0) return [axis, typeof value === "string" ? value : def.levels[0] ?? ""];
    const known = (value && typeof value === "object" ? value : {}) as Record<string, string>;
    return [axis, Object.fromEntries(def.keys.map((k) => [k, known[k] ?? def.levels[0] ?? ""]))];
  })));
  if (axes.length === 0) return <><h3>{t("stepScope")}</h3><p className="text-sm text-muted">{t("noAxes")}</p></>;
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate((profile ? { ...values, profile } : values) as AxisValues, { onSuccess: () => setEditing(false) }); };
  const adopted = register.profiles.find((p) => p.key === current.profile);
  const guide = register.scope_guide;
  const show = (value: unknown) => (typeof value === "string" ? term(value).text : "—");
  const summary = axes.map(([axis, def]) => def.keys.length === 0 ? `${term(axis).text}: ${show(current[axis])}`
    : `${term(axis).text}: ${def.keys.map((k) => `${term(k).text} ${show(((current[axis] ?? {}) as Record<string, string>)[k])}`).join(" · ")}`).join(" — ");
  return <>
    <h3>{t("stepScope")}</h3>
    {register.scope && !editing ? <>
      <p lang={register.term_labels.length ? undefined : "es"}>{summary}</p>
      {adopted ? <p>{t("profileAdopted", { title: english ? adopted.title_en : adopted.title_es })}</p> : null}
      <p className="text-sm text-muted">{t("scopeRecorded", { date: format.dateTime(new Date(register.scope.decided_at), { dateStyle: "medium" }) })}</p>
      {canEdit ? <button className="dashboard-button" onClick={() => setEditing(true)}>{t("changeScope")}</button> : null}
    </> : canEdit ? <form onSubmit={submit} className="scope-form">
      <p className="text-sm text-muted">{t("scopeHelp")}</p>
      {guide && register.axes[guide.axis] ? <ScopeGuide guide={guide} levels={register.axes[guide.axis]!.levels ?? []} term={term}
        onApply={(dims, category) => setValues({ ...values, [guide.axis]: { ...(values[guide.axis] as Record<string, string>), ...dims }, ...(category ? { [guide.category_axis]: category } : {}) })} /> : null}
      {axes.map(([axis, def]) => def.keys.length === 0
        ? <AxisSelect key={axis} label={axis} term={term} levels={def.levels} value={values[axis] as string} onChange={(v) => setValues({ ...values, [axis]: v })} />
        : <fieldset key={axis}><legend lang={term(axis).lang}>{term(axis).text}</legend><div className="scope-dimensions">{def.keys.map((k) =>
          <AxisSelect key={k} label={k} term={term} levels={def.levels} value={(values[axis] as Record<string, string>)[k] ?? ""}
            onChange={(v) => setValues({ ...values, [axis]: { ...(values[axis] as Record<string, string>), [k]: v } })} />)}</div></fieldset>)}
      {register.profiles.length ? <ProfileChoice profiles={register.profiles} value={profile} onChange={setProfile} /> : null}
      {save.isError ? <ErrorMessage error={save.error} /> : null}
      <div className="form-actions"><button type="submit" className="button-primary" disabled={save.isPending}>{t("saveScope")}</button>
        {register.scope ? <button type="button" className="dashboard-button" onClick={() => setEditing(false)}>{t("cancel")}</button> : null}</div>
    </form> : <p className="text-sm text-muted">{t("scopeMissingMember")}</p>}
  </>;
}

type TermLabel = (term: string) => { text: string; lang: string | undefined };
type Profile = Register["profiles"][number];

/** A published compliance profile as a scope option (issue 227); proposals then come from it. */
function ProfileChoice({ profiles, value, onChange }: { profiles: Profile[]; value: string; onChange: (v: string) => void }) {
  const t = useTranslations("register");
  const english = useLocale() === "en";
  const cite = useGuideReference();
  const id = useId();
  const chosen = profiles.find((p) => p.key === value);
  return <div className="scope-profile">
    <span className="axis-select"><label htmlFor={id}>{t("profile")}</label>
      <select id={id} value={value} aria-describedby={`${id}-help`} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("profileNone")}</option>
        {profiles.map((p) => <option key={p.key} value={p.key}>{english ? p.title_en : p.title_es}</option>)}
      </select></span>
    <p id={`${id}-help`} className="text-sm text-muted">{chosen ? english ? chosen.summary_en : chosen.summary_es : t("profileHelp")}</p>
    {chosen ? <p className="text-sm text-muted">{t("profileSources", { refs: chosen.refs.map(cite).join("; ") })} {chosen.reviewed_by ? null : t("profileCandidate")}</p> : null}
  </div>;
}

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
  return <span className="assessment-badges">{overdue ? <span className="overdue-flag"><Icon name="overdue" size={14} />{t("overdue")}</span> : null}<StateBadge item={item} /></span>;
}

/** The person's decision, else "Pendiente" with the proposal as a hint. */
export function StateBadge({ item }: { item: RegisterItem }) {
  const a = item.assessment;
  return a ? <AssessmentState state={a.applicability === "not_applicable" ? "not_applicable" : a.implementation} />
    : <AssessmentState state="pending" hint={item.proposal.decision} />;
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
  return <div className="assessment-card">
    <OwnerField item={item} orgId={orgId} frameworkKey={frameworkKey} canEdit={canEdit} />
    <AgentProposal item={item} orgId={orgId} frameworkKey={frameworkKey} canAssess={canAssess} />
    <AssessmentIntro proposal={item.proposal} />
    {a && !editing ? <>
      <AssessmentFields value={a} dated={a.performed_on ? format.dateTime(new Date(a.performed_on), { dateStyle: "medium" }) : undefined} />
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

/** An API key's pending proposal (mcp-server spec, ADR-005). The agent's words are shown as text;
 * nothing changes until a person who may assess the measure confirms it. */
function AgentProposal({ item, orgId, frameworkKey, canAssess }: { item: RegisterItem; orgId: string; frameworkKey: string; canAssess: boolean }) {
  const t = useTranslations("register");
  const format = useFormatter();
  const decide = useDecideProposal(orgId, frameworkKey);
  const heading = useId();
  const p = item.pending_proposal;
  if (!p) return null;
  return <section className="notice proposal-notice" aria-labelledby={heading}>
    <h4 id={heading}><Icon name="integrations" size={16} />{t("agentProposal")}</h4>
    <p className="text-sm text-muted">{t("agentProposalFrom", { name: p.token_name, date: format.dateTime(new Date(p.proposed_at), { dateStyle: "medium", timeStyle: "short" }) })} <span className="font-mono">{p.token_prefix}…</span></p>
    <AssessmentFields value={p}><div><dt>{t("agentRationale")}</dt><dd>{p.rationale}</dd></div></AssessmentFields>
    <p className="text-sm text-muted">{t("agentProposalHelp")}</p>
    {canAssess ? <div className="proposal-actions">
      <button type="button" className="button-primary" disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, verb: "confirm" })}>{t("confirmProposal")}</button>
      <button type="button" className="dashboard-button" disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, verb: "reject" })}>{t("rejectProposal")}</button>
    </div> : null}
    {decide.isError ? <ErrorMessage error={decide.error} /> : null}
  </section>;
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
