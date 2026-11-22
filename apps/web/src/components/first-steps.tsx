"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { components } from "@/lib/api/schema";
import { registerProgress, useRegister } from "@/lib/api/register-hooks";
import { orgFramework } from "@/lib/org";

type Framework = components["schemas"]["FrameworkSummary"];

/** The next step for the framework with the most requirements; nothing when no framework has any. */
export function FirstSteps({ orgId, frameworks }: { orgId: string; frameworks: Framework[] }) {
  const primary = [...frameworks].sort((a, b) => b.requirements - a.requirements)[0];
  if (!primary || primary.requirements === 0) return null;
  return <Steps orgId={orgId} framework={primary} />;
}

function Steps({ orgId, framework }: { orgId: string; framework: Framework }) {
  const t = useTranslations("dashboard");
  const register = useRegister(orgId, framework.key);
  if (register.isError) return null;
  const data = register.data;
  const progress = registerProgress(data?.items ?? []);
  const steps = [
    { label: t("stepScope"), done: Boolean(data?.scope) },
    { label: t("stepAssess", { assessed: progress.assessed, total: progress.total || framework.requirements }), done: progress.total > 0 && progress.assessed === progress.total },
    { label: t("stepReview"), done: Boolean(data?.review) },
    { label: t("stepExport"), done: false },
  ];
  const started = steps.some((s) => s.done) || progress.assessed > 0;
  return <section aria-labelledby="first-steps-heading" className="first-steps">
    <h2 id="first-steps-heading">{t("firstSteps")}</h2>
    <p className="text-sm text-muted">{t("firstStepsIntro", { framework: framework.name })}</p>
    <ol>{steps.map((step) => <li key={step.label} data-done={step.done ? "true" : "false"}>{step.label}</li>)}</ol>
    <Link href={orgFramework(orgId, framework.key)} className="button-primary first-steps-cta">{t(started ? "continue" : "start", { framework: framework.name })}</Link>
  </section>;
}
