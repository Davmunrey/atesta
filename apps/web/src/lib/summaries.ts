import type { ApiToken } from "@/lib/api/tokens";
import type { AccessReviewSummary, Incident, Policy, TrainingCampaign } from "@/lib/api/routines";

/**
 * Executive summaries for records pages (ui-polish spec): counts from the list the page already
 * loads, so management reads the state without scanning rows. Dates compare as ISO days.
 */
export function policySummary(policies: Policy[], today: string) {
  const overdue = policies.filter((p) => p.latest && p.next_review_on && p.next_review_on < today).length;
  const unapproved = policies.filter((p) => !p.latest).length;
  return { total: policies.length, current: policies.length - overdue - unapproved, overdue, unapproved };
}

export function reviewSummary(reviews: AccessReviewSummary[], today: string) {
  const open = reviews.filter((r) => !r.closed_at);
  return {
    total: reviews.length, open: open.length, closed: reviews.length - open.length,
    pending: open.reduce((n, r) => n + r.pending, 0),
    late: open.filter((r) => r.due_on !== null && r.due_on !== undefined && r.due_on < today).length,
  };
}

export function trainingSummary(campaigns: TrainingCampaign[]) {
  return { total: campaigns.length, open: campaigns.filter((c) => !c.closed_at).length, acknowledged: campaigns.reduce((n, c) => n + c.acknowledged, 0) };
}

/** `running`: open incidents whose next notice is still within its deadline; `nextDue` the soonest. */
export function incidentSummary(incidents: Pick<Incident, "closed_at" | "overdue" | "next_due_at">[]) {
  const open = incidents.filter((i) => !i.closed_at);
  const running = open.filter((i) => i.overdue === 0 && i.next_due_at);
  const nextDue = running.map((i) => i.next_due_at!).sort((a, b) => new Date(a).getTime() - new Date(b).getTime())[0] ?? null;
  return { open: open.length, closed: incidents.length - open.length, overdue: open.filter((i) => i.overdue > 0).length, running: running.length, nextDue };
}

export function tokenSummary(tokens: ApiToken[], now: Date) {
  const active = tokens.filter((t) => !t.revoked_at && new Date(t.expires_at) > now).length;
  const used = tokens.map((t) => t.last_used_at).filter((d): d is string => Boolean(d)).sort();
  return { active, inactive: tokens.length - active, lastUsed: used.at(-1) ?? null };
}

export function overdueTrainings(campaigns: Pick<TrainingCampaign, "closed_at" | "closes_on">[], today: string) {
  return campaigns.filter((c) => !c.closed_at && c.closes_on < today).length;
}
