"use client";

import Link from "next/link";
import { useFormatter, useLocale, useNow, useTranslations } from "next-intl";
import { useActivity, useMembers } from "@/lib/api/hooks";
import { isMyWorkOverdue, type Readiness, useMyWork } from "@/lib/api/register-hooks";
import { type Membership, orgActivity, orgFramework, orgMembers, orgMyWork } from "@/lib/org";
import { canReviewControls, isContributor } from "@/lib/permissions";
import { RankedBars } from "./charts";

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
  return <section aria-labelledby="attention-heading" className="attention">
    <h2 id="attention-heading">{t("now")}</h2>
    {items.length === 0 ? <p className="text-muted">
      {t("calm")}{" "}
      {next ? <Link href={orgFramework(orgId, next.key)} className="text-link underline">{t(`step.${nextStep(next).kind}`, { count: nextStep(next).count, framework: next.name })}</Link> : null}
    </p> : <ul className="attention-list">
      {items.map((item) => <li key={item.key} data-severity={item.severity}>
        <span className="attention-tag">{t(`severity.${item.severity}`)}</span>
        <Link href={item.href}>{item.text}</Link>
      </li>)}
    </ul>}
  </section>;
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
  return <section aria-labelledby="your-work-heading" className="cockpit-panel">
    <h2 id="your-work-heading">{t("yourWork")}</h2>
    {items.length === 0 ? <p className="text-sm text-muted">{t("yourWorkEmpty")}</p> : <ul className="cockpit-list">
      {items.map((i) => <li key={`${i.framework_key}:${i.code}`}>
        <Link href={`${orgFramework(org.organization_id, i.framework_key)}#req-${encodeURIComponent(i.code)}`}>
          <span className="requirement-code">{i.code}</span> <span lang={english && !i.title_en ? "es" : undefined}>{english ? i.title_en ?? i.title_es : i.title_es}</span>
        </Link>
        <span className="text-sm text-muted">
          {i.due_on ? format.dateTime(new Date(`${i.due_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) : t("noDue")}
          {isMyWorkOverdue(i, today) ? <> · <span data-severity="overdue">{t("severity.overdue")}</span></> : null}
        </span>
      </li>)}
    </ul>}
    <Link href={orgMyWork(org.organization_id)} className="text-link underline text-sm">{t("allMyWork")}</Link>
  </section>;
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
  return <section aria-labelledby="team-heading" className="cockpit-panel">
    <h2 id="team-heading">{t("team")}</h2>
    <RankedBars title={t("teamChart")} rows={rows} empty={t("teamEmpty")} />
  </section>;
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
  return <section aria-labelledby="recent-heading" className="cockpit-panel">
    <h2 id="recent-heading">{t("recent")}</h2>
    {events.length === 0 ? <p className="text-sm text-muted">{t("recentEmpty")}</p> : <ul className="cockpit-list">
      {events.map((e, i) => <li key={`${e.occurred_at}:${i}`}>
        <span>{action(e.action)}</span>
        <span className="text-sm text-muted">{e.actor_email ?? t("system")} · {format.relativeTime(new Date(e.occurred_at), now)}</span>
      </li>)}
    </ul>}
    <Link href={orgActivity(org.organization_id)} className="text-link underline text-sm">{t("allActivity")}</Link>
  </section>;
}
