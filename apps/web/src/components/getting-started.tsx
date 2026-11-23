"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useSyncExternalStore } from "react";
import { useMembers } from "@/lib/api/hooks";
import type { Readiness } from "@/lib/api/register-hooks";
import { useAccessReviews, usePolicies, useTrainingCampaigns } from "@/lib/api/routines";
import { useApiTokens } from "@/lib/api/tokens";
import { type Membership, orgAccessReviews, orgDossier, orgFramework, orgIntegrations, orgInvitations, orgPolicies } from "@/lib/org";
import { canReviewControls } from "@/lib/permissions";
import { Icon } from "./icons";
import { Panel } from "./page-frame";

export const FIRST_ASSESSMENTS = 10;
const KEY = (orgId: string) => `atesta_getting_started_hidden:${orgId}`;

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const listeners = new Set<() => void>();
function subscribe(l: () => void) { listeners.add(l); return () => listeners.delete(l); }

/** The framework the checklist leads with: the one with selection axes (ENS) or the largest. */
export function leadFramework(readiness: Readiness[]): Readiness | undefined {
  return [...readiness].sort((a, b) => Number(b.has_axes) - Number(a.has_axes) || b.total - a.total)[0];
}

/**
 * Getting started (owner decision, 2026-11-23: the first value is "everything"). Each step is
 * marked done from the organization's own records; admins see it until it is complete or hidden.
 */
export function GettingStarted({ org, readiness }: { org: Membership; readiness: Readiness[] }) {
  const t = useTranslations("gettingStarted");
  const id = org.organization_id;
  const admin = canReviewControls(org.role);
  const hidden = useSyncExternalStore(subscribe, () => storage()?.getItem(KEY(id)) === "1", () => true);
  const members = useMembers(id, admin);
  const policies = usePolicies(id);
  const reviews = useAccessReviews(id);
  const trainings = useTrainingCampaigns(id);
  const tokens = useApiTokens(id, admin);
  const lead = leadFramework(readiness);
  if (!admin || hidden || !lead) return null;
  const assessed = readiness.reduce((n, r) => n + r.assessed, 0);
  const steps = [
    { key: "scope", done: lead.has_axes ? lead.scope_defined : lead.assessed > 0, href: orgFramework(id, lead.key), values: { framework: lead.name } },
    { key: "assess", done: assessed >= FIRST_ASSESSMENTS, href: orgFramework(id, lead.key), values: { count: Math.min(assessed, FIRST_ASSESSMENTS), total: FIRST_ASSESSMENTS } },
    { key: "team", done: (members.data?.length ?? 0) > 1, href: orgInvitations(id), values: {} },
    { key: "policy", done: (policies.data ?? []).some((p) => p.latest), href: orgPolicies(id), values: {} },
    { key: "routine", done: (reviews.data?.length ?? 0) > 0 || (trainings.data?.length ?? 0) > 0, href: orgAccessReviews(id), values: {} },
    { key: "tool", done: (tokens.data?.length ?? 0) > 0, href: orgIntegrations(id), values: {} },
    { key: "dossier", done: Boolean(lead.review_on), href: orgDossier(id, lead.key), values: { framework: lead.name } },
  ] as const;
  const done = steps.filter((s) => s.done).length;
  if (done === steps.length) return null;
  function hide() {
    storage()?.setItem(KEY(id), "1");
    listeners.forEach((l) => l());
  }
  return <Panel title={t("title")} description={t("progress", { done, total: steps.length })}
    actions={<button type="button" className="dashboard-button" onClick={hide}>{t("hide")}</button>}>
    <ol className="getting-started">{steps.map((s) => <li key={s.key} data-done={s.done ? "true" : "false"}>
      <Icon name={s.done ? "done" : "pending"} />
      <span className="min-w-0"><Link href={s.href} className="text-link underline">{t(`steps.${s.key}.title`, s.values)}</Link>
        <span className="block text-sm text-muted">{s.done ? t("done") : t(`steps.${s.key}.help`)}</span></span>
    </li>)}</ol>
  </Panel>;
}
