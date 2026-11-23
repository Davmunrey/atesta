"use client";

import Link from "next/link";
import { useFormatter, useLocale, useNow, useTranslations } from "next-intl";
import { useActivity, useMembers } from "@/lib/api/hooks";
import { isMyWorkOverdue, type Readiness, useMyWork } from "@/lib/api/register-hooks";
import { useRoutinesDue } from "@/lib/api/routines";
import { type Membership, orgAccessReview, orgActivity, orgFramework, orgIncident, orgMembers, orgMyWork, orgPolicies, orgTrainingCampaign } from "@/lib/org";
import { canReviewControls, isContributor } from "@/lib/permissions";
import { RankedBars } from "./charts";
import { Icon } from "./icons";
import { Panel } from "./page-frame";

export type Step = { kind: "scope" | "assess" | "review" | "export"; count: number };
export type Attention = { key: string; severity: "overdue" | "missing" | "pending"; text: string; href: string };

const AUDITOR_WARNING_DAYS = 14;

/** The one next step of a framework, in the order the self-assessment flows (requirement-register spec). */
export function nextStep(r: Readiness): Step {
  if (r.has_axes && !r.scope_defined) return { kind: "scope", count: 0 };
  if (r.assessed < r.total) return { kind: "assess", count: r.total - r.assessed };
  if (!r.review_on) return { kind: "review", count: 0 };
  return { kind: "export", count: 0 };
}

export const started = (r: Readiness) => r.assessed > 0 || r.scope_defined;

/** What needs attention now, most urgent first; only true items, each with where it is solved. */
export function useAttention(org: Membership, readiness: Readiness[]): Attention[] {
  const t = useTranslations("cockpit.attention");
  const format = useFormatter();
  const now = useNow();
  const admin = canReviewControls(org.role);
  const members = useMembers(org.organization_id, admin);
  const items: Attention[] = [];
  const at = (r: Readiness) => orgFramework(org.organization_id, r.key);
  for (const r of readiness.filter((x) => x.overdue > 0)) {
    items.push({ key: `overdue:${r.key}`, severity: "overdue", text: t("overdue", { count: r.overdue, framework: r.name }), href: at(r) });
  }
  for (const r of readiness.filter((x) => x.total > 0 && x.assessed === x.total && !x.review_on)) {
    items.push({ key: `review:${r.key}`, severity: "missing", text: t("review", { framework: r.name }), href: at(r) });
  }
  for (const r of readiness.filter((x) => started(x) && x.unowned_open > 0)) {
    items.push({ key: `unowned:${r.key}`, severity: "pending", text: t("unowned", { count: r.unowned_open, framework: r.name }), href: at(r) });
  }
  for (const r of readiness.filter((x) => x.assessed > 0 && x.has_axes && !x.scope_defined)) {
    items.push({ key: `scope:${r.key}`, severity: "missing", text: t("scope", { framework: r.name }), href: at(r) });
  }
  const due = useRoutinesDue(org.organization_id);
  const english = useLocale() === "en";
  const id = org.organization_id;
  const hrefs = {
    policy_review: () => orgPolicies(id), policy_unapproved: () => orgPolicies(id),
    access_review_overdue: (d: string) => orgAccessReview(id, d), training_unclosed: (d: string) => orgTrainingCampaign(id, d),
    incident_clock: (d: string) => orgIncident(id, d),
  } as const;
  for (const d of due.data ?? []) {
    const date = d.due_on ? format.dateTime(new Date(`${d.due_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) : "";
    const severity = d.overdue ? "overdue" : d.kind === "policy_unapproved" ? "missing" : "pending";
    const href = hrefs[d.kind](d.id);
    if (d.kind === "incident_clock" && d.clock && d.due_at) {
      const when = t(d.overdue ? "due.clockOverdue" : "due.clockRunning", { time: format.dateTime(new Date(d.due_at), { dateStyle: "medium", timeStyle: "short" }) });
      items.push({ key: `due:${d.kind}:${d.id}:${d.clock.en}:${d.clock.framework}`, severity, href,
        text: t("due.incident_clock", { clock: english ? d.clock.en : d.clock.es, framework: d.clock.framework, title: d.title, when }) });
      continue;
    }
    items.push({ key: `due:${d.kind}:${d.id}`, severity, text: t(`due.${d.kind}`, { title: d.title, date }), href });
  }
  const soon = now.getTime() + AUDITOR_WARNING_DAYS * 86_400_000;
  for (const m of members.data ?? []) {
    if (m.role !== "auditor" || !m.access_expires_on) continue;
    const ends = new Date(`${m.access_expires_on}T00:00:00Z`);
    if (ends.getTime() <= soon) {
      const date = format.dateTime(ends, { dateStyle: "long", timeZone: "UTC" });
      items.push({ key: `auditor:${m.user_id}`, severity: "pending", text: t("auditor", { email: m.email, date }), href: orgMembers(org.organization_id) });
    }
  }
  return items;
}

/** One sentence that a busy reader can stop at: where each framework in progress stands. */
export function ReadinessSummary({ readiness, attention }: { readiness: Readiness[]; attention: number }) {
  const t = useTranslations("cockpit");
  const active = readiness.filter(started);
  if (active.length === 0) return null;
  return <p className="readiness-summary">
    {active.map((r) => <span key={r.key}>{t("summary", { framework: r.name, assessed: r.assessed, total: r.total, implemented: r.implemented })} </span>)}
    <span>{attention > 0 ? t("summaryAttention", { count: attention }) : t("summaryCalm")}</span>
  </p>;
}

export function AttentionList({ items, readiness, orgId }: { items: Attention[]; readiness: Readiness[]; orgId: string }) {
  const t = useTranslations("cockpit");
  const next = readiness.filter(started).concat(readiness).find((r) => nextStep(r).kind !== "export");
  return <Panel title={t("now")} className="attention">
    {items.length === 0 ? <p className="text-muted">
      {t("calm")}{" "}
      {next ? <Link href={orgFramework(orgId, next.key)} className="text-link underline">{t(`step.${nextStep(next).kind}`, { count: nextStep(next).count, framework: next.name })}</Link> : null}
    </p> : <ul className="attention-list">
      {items.map((item) => <li key={item.key} data-severity={item.severity}>
        <span className="badge attention-tag" data-severity={item.severity}><Icon name={item.severity} />{t(`severity.${item.severity}`)}</span>
        <Link href={item.href}>{item.text}</Link>
      </li>)}
    </ul>}
  </Panel>;
}

const SEGMENTS = ["implemented", "partial", "not_implemented", "not_applicable"] as const;

/** Decorative: the same counts are always written next to it. */
export function ReadinessBar({ r }: { r: Readiness }) {
  if (r.total === 0) return null;
  const widths = SEGMENTS.map((s) => (r[s] / r.total) * 100);
  const offsets = widths.map((_, i) => widths.slice(0, i).reduce((sum, w) => sum + w, 0));
  return <svg className="readiness-bar" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true">
    <rect className="readiness-track" x="0" width="100" height="4" />
    {SEGMENTS.map((s, i) => <rect key={s} data-readiness={s} x={offsets[i]} width={widths[i]} height="4" />)}
  </svg>;
}

export function ReadinessCounts({ r }: { r: Readiness }) {
  const t = useTranslations("cockpit");
  return <span className="readiness-counts">
    {t("counts", { assessed: r.assessed, total: r.total, implemented: r.implemented, partial: r.partial, notImplemented: r.not_implemented, notApplicable: r.not_applicable })}
  </span>;
}

export function StepLink({ r, orgId }: { r: Readiness; orgId: string }) {
  const t = useTranslations("cockpit.step");
  const step = nextStep(r);
  return <Link href={orgFramework(orgId, r.key)} className="readiness-step">{t(step.kind, { count: step.count, framework: r.name })}</Link>;
}

/** The signed-in person's next measures, soonest due first. */
export function YourWork({ org }: { org: Membership }) {
  const t = useTranslations("cockpit");
  const format = useFormatter();
  const english = useLocale() === "en";
  const now = useNow();
  const query = useMyWork(org.organization_id);
  if (!isContributor(org.role) || !query.data) return null;
  const today = now.toISOString().slice(0, 10);
  const items = query.data.filter((i) => !(i.applicability === "not_applicable" || i.implementation === "implemented")).slice(0, 3);
  return <Panel title={t("yourWork")} actions={<Link href={orgMyWork(org.organization_id)} className="text-link underline text-sm action-link">{t("allMyWork")}</Link>}>
    {items.length === 0 ? <p className="text-sm text-muted">{t("yourWorkEmpty")}</p> : <ul className="cockpit-list">
      {items.map((i) => <li key={`${i.framework_key}:${i.code}`}>
        <Link href={`${orgFramework(org.organization_id, i.framework_key)}#req-${encodeURIComponent(i.code)}`}>
          <span className="requirement-code">{i.code}</span> <span lang={english && !i.title_en ? "es" : undefined}>{english ? i.title_en ?? i.title_es : i.title_es}</span>
        </Link>
        <span className="text-sm text-muted">
          {i.due_on ? format.dateTime(new Date(`${i.due_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) : t("noDue")}
          {isMyWorkOverdue(i, today) ? <> · <span className="badge" data-severity="overdue"><Icon name="overdue" />{t("severity.overdue")}</span></> : null}
        </span>
      </li>)}
    </ul>}
  </Panel>;
}

/** Open measures per person across frameworks. Not for auditors, who do not see people. */
export function TeamLoad({ org, readiness }: { org: Membership; readiness: Readiness[] }) {
  const t = useTranslations("cockpit");
  const show = isContributor(org.role);
  const members = useMembers(org.organization_id, show);
  if (!show || !members.isSuccess) return null;
  const totals = new Map<string, number>();
  for (const r of readiness) for (const [user, n] of Object.entries(r.open_by_owner)) totals.set(user, (totals.get(user) ?? 0) + n);
  const emails = new Map(members.data.map((m) => [m.user_id, m.email]));
  const rows = [...totals.entries()].map(([id, value]) => ({ id, label: emails.get(id) ?? t("formerMember"), value }));
  return <Panel title={t("team")}>
    <RankedBars title={t("teamChart")} rows={rows} empty={t("teamEmpty")} />
  </Panel>;
}

/** The latest events, for admins and owners (insights spec). */
export function RecentActivity({ org }: { org: Membership }) {
  const t = useTranslations("cockpit");
  const activity = useTranslations("activity");
  const format = useFormatter();
  const now = useNow();
  const admin = canReviewControls(org.role);
  const query = useActivity(org.organization_id, 30, admin);
  if (!admin || !query.data) return null;
  const action = (name: string) => { const key = `actions.${name.replaceAll(".", "_")}`; return activity.has(key) ? activity(key) : name; };
  const events = query.data.events.slice(0, 5);
  return <Panel title={t("recent")} actions={<Link href={orgActivity(org.organization_id)} className="text-link underline text-sm action-link">{t("allActivity")}</Link>}>
    {events.length === 0 ? <p className="text-sm text-muted">{t("recentEmpty")}</p> : <ul className="cockpit-list">
      {events.map((e, i) => <li key={`${e.occurred_at}:${i}`}>
        <span>{action(e.action)}</span>
        <span className="text-sm text-muted">{e.actor_email ?? t("system")} · {format.relativeTime(new Date(e.occurred_at), now)}</span>
      </li>)}
    </ul>}
  </Panel>;
}

/** Key figures across frameworks in progress (console-shell spec); state is written, not only coloured. */
export function Kpis({ readiness }: { readiness: Readiness[] }) {
  const c = useTranslations("console.kpi");
  const label = useTranslations("console");
  const format = useFormatter();
  const active = readiness.filter(started);
  const sum = (pick: (r: Readiness) => number) => active.reduce((n, r) => n + pick(r), 0);
  const overdue = sum((r) => r.overdue);
  const unowned = sum((r) => r.unowned_open);
  const state = (n: number) => <dd className="kpi-state" data-severity={n > 0 ? "overdue" : "done"}>
    <Icon name={n > 0 ? "overdue" : "done"} width={16} height={16} />{c(n > 0 ? "act" : "clear")}</dd>;
  return <dl className="kpis" aria-label={label("kpis")}>
    <div className="kpi"><dt>{c("inProgress")}</dt><dd>{format.number(active.length)}</dd><dd className="kpi-meta">{c("ofTotal", { total: readiness.length })}</dd></div>
    <div className="kpi"><dt>{c("assessed")}</dt><dd>{format.number(sum((r) => r.assessed))}</dd><dd className="kpi-meta">{c("ofTotal", { total: sum((r) => r.total) })}</dd></div>
    <div className="kpi"><dt>{c("implemented")}</dt><dd>{format.number(sum((r) => r.implemented))}</dd><dd className="kpi-meta">{c("ofTotal", { total: sum((r) => r.total) })}</dd></div>
    <div className="kpi"><dt>{c("overdue")}</dt><dd>{format.number(overdue)}</dd>{state(overdue)}</div>
    <div className="kpi"><dt>{c("unowned")}</dt><dd>{format.number(unowned)}</dd>{state(unowned)}</div>
  </dl>;
}
