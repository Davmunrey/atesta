"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useFormatter, useLocale, useNow, useTranslations } from "next-intl";
import { useMembers } from "@/lib/api/hooks";
import { isMyWorkOverdue, type MyWorkItem, type Readiness, useMyWork } from "@/lib/api/register-hooks";
import { useRoutinesDue } from "@/lib/api/routines";
import { type Membership, orgAccessReview, orgFramework, orgIncident, orgMembers, orgMyWork, orgPolicies, orgTrainingCampaign } from "@/lib/org";
import { canReviewControls, isContributor } from "@/lib/permissions";
import { Badge, ClockBadge } from "./badge";
import { Panel } from "./page-frame";

export type Step = { kind: "scope" | "assess" | "review" | "export"; count: number };
/**
 * One task on the home (console-unification spec). `group` orders the list: 0 running legal
 * clocks, 1 overdue, 2 my measures due this week, 3 the rest; `due` (epoch ms) orders a group.
 */
export type Attention = {
  key: string; severity: "clock" | "overdue" | "missing" | "pending"; text: ReactNode; href: string;
  group: 0 | 1 | 2 | 3; due: number; dueAt?: string; label?: string;
};

const AUDITOR_WARNING_DAYS = 14;
const WEEK_DAYS = 7;
const DAY = 86_400_000;
const LATER = Number.MAX_SAFE_INTEGER;
const dayStart = (iso: string) => new Date(`${iso}T00:00:00Z`).getTime();

/** The one next step of a framework, in the order the self-assessment flows (requirement-register spec). */
export function nextStep(r: Readiness): Step {
  if (r.has_axes && !r.scope_defined) return { kind: "scope", count: 0 };
  if (r.assessed < r.total) return { kind: "assess", count: r.total - r.assessed };
  if (!r.review_on) return { kind: "review", count: 0 };
  return { kind: "export", count: 0 };
}

export const started = (r: Readiness) => r.assessed > 0 || r.scope_defined;

/** Legal clocks first, then overdue, then my week, then the rest; soonest first in each group. */
export function orderTasks(items: Attention[]): Attention[] {
  return [...items].sort((a, b) => a.group - b.group || a.due - b.due);
}

const open = (i: MyWorkItem) => !(i.applicability === "not_applicable" || i.implementation === "implemented");

/** Everything that needs someone now, as one ordered list; only true items, each with where it is solved. */
export function useAttention(org: Membership, readiness: Readiness[]): Attention[] {
  const t = useTranslations("cockpit.attention");
  const format = useFormatter();
  const now = useNow();
  const english = useLocale() === "en";
  const id = org.organization_id;
  const admin = canReviewControls(org.role);
  const members = useMembers(id, admin);
  const work = useMyWork(id);
  const due = useRoutinesDue(id);
  const items: Attention[] = [];
  const at = (r: Readiness) => orgFramework(id, r.key);
  const today = now.toISOString().slice(0, 10);
  const day = (iso: string) => format.dateTime(new Date(`${iso}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" });
  const mine = isContributor(org.role) ? (work.data ?? []).filter(open) : [];
  const weekEnd = dayStart(today) + WEEK_DAYS * DAY;
  for (const i of mine) {
    if (!i.due_on) continue;
    const overdue = isMyWorkOverdue(i, today);
    if (!overdue && dayStart(i.due_on) > weekEnd) continue; // later work lives in Mi trabajo
    const title = english ? i.title_en ?? i.title_es : i.title_es;
    items.push({ key: `mine:${i.framework_key}:${i.code}`, severity: overdue ? "overdue" : "pending", group: overdue ? 1 : 2, due: dayStart(i.due_on),
      label: overdue ? undefined : day(i.due_on), href: `${orgFramework(id, i.framework_key)}#req-${encodeURIComponent(i.code)}`,
      text: <><span className="requirement-code">{i.code}</span> <span lang={english && !i.title_en ? "es" : undefined}>{title}</span>{overdue ? ` · ${t("mineOverdue", { date: day(i.due_on) })}` : null}</> });
  }
  for (const r of readiness.filter((x) => x.overdue > 0)) {
    const listed = mine.filter((i) => i.framework_key === r.key && isMyWorkOverdue(i, today)).length;
    const others = r.overdue - listed;
    if (others <= 0) continue;
    items.push({ key: `overdue:${r.key}`, severity: "overdue", group: 1, due: LATER, href: at(r),
      text: t(listed > 0 ? "overdueOthers" : "overdue", { count: others, framework: r.name }) });
  }
  for (const r of readiness.filter((x) => x.total > 0 && x.assessed === x.total && !x.review_on)) {
    items.push({ key: `review:${r.key}`, severity: "missing", group: 3, due: LATER, text: t("review", { framework: r.name }), href: at(r) });
  }
  for (const r of readiness.filter((x) => started(x) && x.unowned_open > 0)) {
    items.push({ key: `unowned:${r.key}`, severity: "pending", group: 3, due: LATER, text: t("unowned", { count: r.unowned_open, framework: r.name }), href: at(r) });
  }
  for (const r of readiness.filter((x) => x.assessed > 0 && x.has_axes && !x.scope_defined)) {
    items.push({ key: `scope:${r.key}`, severity: "missing", group: 3, due: LATER, text: t("scope", { framework: r.name }), href: at(r) });
  }
  const hrefs = {
    policy_review: () => orgPolicies(id), policy_unapproved: () => orgPolicies(id),
    access_review_overdue: (d: string) => orgAccessReview(id, d), training_unclosed: (d: string) => orgTrainingCampaign(id, d),
    incident_clock: (d: string) => orgIncident(id, d),
  } as const;
  for (const d of due.data ?? []) {
    const date = d.due_on ? format.dateTime(new Date(`${d.due_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) : "";
    const href = hrefs[d.kind](d.id);
    if (d.kind === "incident_clock" && d.clock && d.due_at) {
      const when = t(d.overdue ? "due.clockOverdue" : "due.clockRunning", { time: format.dateTime(new Date(d.due_at), { dateStyle: "medium", timeStyle: "short" }) });
      items.push({ key: `due:${d.kind}:${d.id}:${d.clock.en}:${d.clock.framework}`, severity: d.overdue ? "overdue" : "clock", group: 0,
        due: new Date(d.due_at).getTime(), dueAt: d.due_at, href,
        text: t("due.incident_clock", { clock: english ? d.clock.en : d.clock.es, framework: d.clock.framework, title: d.title, when }) });
      continue;
    }
    const severity = d.overdue ? "overdue" : d.kind === "policy_unapproved" ? "missing" : "pending";
    items.push({ key: `due:${d.kind}:${d.id}`, severity, group: d.overdue ? 1 : 3, due: d.due_on ? dayStart(d.due_on) : LATER,
      text: t(`due.${d.kind}`, { title: d.title, date }), href });
  }
  const soon = now.getTime() + AUDITOR_WARNING_DAYS * DAY;
  for (const m of members.data ?? []) {
    if (m.role !== "auditor" || !m.access_expires_on) continue;
    const ends = new Date(`${m.access_expires_on}T00:00:00Z`);
    if (ends.getTime() <= soon) {
      items.push({ key: `auditor:${m.user_id}`, severity: "pending", group: 3, due: ends.getTime(), href: orgMembers(id),
        text: t("auditor", { email: m.email, date: format.dateTime(ends, { dateStyle: "long", timeZone: "UTC" }) }) });
    }
  }
  return orderTasks(items);
}

/** The home's first region: one ordered task list, with the next step when nothing is urgent. */
export function AttentionList({ items, readiness, org }: { items: Attention[]; readiness: Readiness[]; org: Membership }) {
  const t = useTranslations("cockpit");
  const orgId = org.organization_id;
  const next = readiness.filter(started).concat(readiness).find((r) => nextStep(r).kind !== "export");
  return <Panel title={t("now")} className="attention"
    actions={isContributor(org.role) ? <Link href={orgMyWork(orgId)} className="text-link underline text-sm action-link">{t("allMyWork")}</Link> : null}>
    {items.length === 0 ? <p className="text-muted">
      {t("calm")}{" "}
      {next ? <Link href={orgFramework(orgId, next.key)} className="text-link underline">{t(`step.${nextStep(next).kind}`, { count: nextStep(next).count, framework: next.name })}</Link> : null}
    </p> : <ul className="attention-list">
      {items.map((item) => <li key={item.key} data-severity={item.severity}>
        {item.dueAt ? <ClockBadge dueAt={item.dueAt} className="attention-tag" />
          : <Badge severity={item.severity} className="attention-tag">{item.label ?? t(`severity.${item.severity}`)}</Badge>}
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
