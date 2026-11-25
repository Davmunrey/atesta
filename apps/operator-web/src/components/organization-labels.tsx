"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@atesta/ui/badge";
import type { Health, OrgState } from "@/lib/api/organizations";

const STATE = { active: "orgActive", suspended: "orgSuspended", closing: "orgClosing" } as const;
const HEALTH = { ok: "healthOk", attention: "healthAttention", pending: "healthPending", none: "healthNone" } as const;

/** An organization's state and its connections' health, from the shared severity mapping. */
export function StateBadge({ state }: { state: OrgState }) {
  return <Badge state={STATE[state]}>{useTranslations("organizations.states")(state)}</Badge>;
}

export function HealthBadge({ health }: { health: Health }) {
  return <Badge state={HEALTH[health]}>{useTranslations("organizations.health")(health)}</Badge>;
}

/** "Pro", or "Business (por defecto)" when the organization has no plan set yet. */
export function PlanName({ plan, isDefault }: { plan: string; isDefault: boolean }) {
  const t = useTranslations("organizations");
  return <>{isDefault ? t("defaultPlan", { plan: t(`plans.${plan}`) }) : t(`plans.${plan}`)}</>;
}
