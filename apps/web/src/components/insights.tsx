"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useMembers } from "@/lib/api/hooks";
import {
  isOverdue, registerProgress, useRegisterHistory, useScoreTrend, workload, type Register,
} from "@/lib/api/register-hooks";
import { LineChart, RankedBars, StatTiles } from "./charts";

type Ctx = { orgId: string; frameworkKey: string; register: Register };

/** Where the self-assessment stands and how it moved (insights spec). Only recorded data. */
export function ProgressInsights({ orgId, frameworkKey, register }: Ctx) {
  const t = useTranslations("insights");
  const format = useFormatter();
  const history = useRegisterHistory(orgId, frameworkKey);
  const trend = useScoreTrend(orgId, frameworkKey);
  const p = registerProgress(register.items);
  const day = (iso: string) => format.dateTime(new Date(`${iso}T00:00:00`), { day: "numeric", month: "short" });
  const points = (history.data ?? []).map((h) => ({ label: day(h.day), value: h.implemented }));
  const scores = (trend.data ?? []).filter((s) => s.score !== null)
    .map((s) => ({ label: format.dateTime(new Date(s.computed_at), { day: "numeric", month: "short" }), value: s.score ?? 0 }));
  return <section aria-labelledby="insights-heading" className="insights">
    <h2 id="insights-heading">{t("title")}</h2>
    <StatTiles tiles={[
      { label: t("assessed"), value: `${p.assessed} / ${p.total}` },
      { label: t("implemented"), value: p.implemented },
      { label: t("notApplicable"), value: p.notApplicable },
      { label: t("pending"), value: p.total - p.assessed },
    ]} />
    {points.length >= 2
      ? <LineChart title={t("implementedOverTime")} points={points} valueLabel={t("implemented")} tableLabel={t("showTable")} integer />
      : <p className="text-sm text-muted">{t("historyHelp")}</p>}
    {scores.length >= 2
      ? <LineChart title={t("scoreOverTime")} points={scores} valueLabel={t("score")} tableLabel={t("showTable")} format={(v) => `${format.number(v, { maximumFractionDigits: 1 })} %`} />
      : null}
  </section>;
}

/** Who holds the open measures, and what is overdue (insights spec). */
export function OwnerInsights({ orgId, register }: Omit<Ctx, "frameworkKey">) {
  const t = useTranslations("insights");
  const members = useMembers(orgId);
  const emails = new Map((members.data ?? []).map((m) => [m.user_id, m.email]));
  const load = workload(register.items);
  const today = new Date().toISOString().slice(0, 10);
  const overdue = register.items.filter((i) => isOverdue(i, today)).length;
  const rows = [...load.entries()].filter(([owner]) => owner !== null)
    .map(([owner, value]) => ({ label: emails.get(owner!) ?? t("formerMember"), value }));
  return <section aria-labelledby="owners-heading" className="insights">
    <h2 id="owners-heading">{t("owners")}</h2>
    <StatTiles tiles={[
      { label: t("unowned"), value: load.get(null) ?? 0 },
      { label: t("overdue"), value: overdue },
    ]} />
    <RankedBars title={t("openByOwner")} rows={rows} empty={t("noOwners")} />
  </section>;
}
