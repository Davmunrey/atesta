"use client";

import { useFormatter, useTranslations } from "next-intl";
import type { ApiToken } from "@/lib/api/tokens";
import type { AccessReviewSummary, Incident, Policy, TrainingCampaign } from "@/lib/api/routines";
import { incidentSummary, overdueTrainings, policySummary, reviewSummary, tokenSummary } from "@/lib/summaries";
import { Badge, ClockBadge } from "@atesta/ui/badge";

/** What a register needs now: the figures that need action (written), or why nothing does.
 *  `clock` is the soonest running legal deadline, when one runs and nothing is overdue. */
export type RecordState = { needs: string[]; calm: string; clock?: string | null };

/** The one reading of each register, shared by its page and the home's Registros (console-unification spec). */
export function useRecordStates() {
  const t = useTranslations("summary");
  const today = new Date().toISOString().slice(0, 10);
  const some = (...parts: (string | false)[]) => parts.filter((p): p is string => Boolean(p));
  return {
    policies: (list: Policy[]): RecordState => {
      const s = policySummary(list, today);
      return { needs: some(s.overdue > 0 && t("policies.overdue", { count: s.overdue }), s.unapproved > 0 && t("policies.unapproved", { count: s.unapproved })), calm: t("policies.calm") };
    },
    access: (list: AccessReviewSummary[]): RecordState => {
      const s = reviewSummary(list, today);
      return { needs: some(s.late > 0 && t("access.late", { count: s.late }), s.pending > 0 && t("access.pending", { count: s.pending })), calm: t(s.open > 0 ? "access.calmOpen" : "access.calm") };
    },
    training: (list: TrainingCampaign[]): RecordState => {
      const late = overdueTrainings(list, today);
      return { needs: some(late > 0 && t("training.late", { count: late })), calm: t(list.some((c) => !c.closed_at) ? "training.calmOpen" : "training.calm") };
    },
    incidents: (list: Pick<Incident, "closed_at" | "overdue" | "next_due_at">[]): RecordState => {
      const s = incidentSummary(list);
      return { needs: some(s.overdue > 0 && t("incidents.overdue", { count: s.overdue }), s.running > 0 && t("incidents.running", { count: s.running })),
        calm: t("incidents.calm"), clock: s.overdue > 0 ? null : s.nextDue };
    },
    tokens: (list: ApiToken[]): RecordState => {
      const s = tokenSummary(list, new Date());
      return { needs: some(s.active === 0 && t("tokens.none")), calm: t("tokens.calm") };
    },
  };
}

/** The state of a register as one badge: needs action, a running clock's countdown, or up to date. */
export function RecordBadge({ state }: { state: RecordState }) {
  const c = useTranslations("console.kpi");
  if (state.clock) return <ClockBadge dueAt={state.clock} />;
  return state.needs.length > 0 ? <Badge state="recordsAct">{c("act")}</Badge> : <Badge state="recordsClear">{c("clear")}</Badge>;
}

/** The sentence: the figures that need action, inline, or why nothing does. */
export function useRecordSentence() {
  const t = useTranslations("summary");
  const format = useFormatter();
  return (state: RecordState) => state.needs.length > 0 ? t("needs", { list: format.list(state.needs, { type: "conjunction" }) }) : state.calm;
}

/** The records-page pattern (DESIGN.md): one sentence with only what needs action, then the register. */
export function RecordSummary({ state }: { state: RecordState }) {
  const sentence = useRecordSentence();
  return <p className="record-summary"><RecordBadge state={state} /> <span>{sentence(state)}</span></p>;
}
