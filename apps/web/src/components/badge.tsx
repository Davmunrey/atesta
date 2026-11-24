"use client";

import { useNow, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { countdown } from "@/lib/deadline";
import { Icon } from "./icons";

/** The severity scale (DESIGN.md, severity mapping): each severity has one icon and one colour. */
export type Severity = "clock" | "overdue" | "missing" | "pending" | "done";
const ICON: Record<Severity, string> = { clock: "pending", overdue: "overdue", missing: "missing", pending: "pending", done: "done" };

/** A state written as icon plus text; colour reinforces, never carries it. */
export function Badge({ severity, children, className }: { severity: Severity; children: ReactNode; className?: string }) {
  return <span className={`badge${className ? ` ${className}` : ""}`} data-severity={severity}><Icon name={ICON[severity]} />{children}</span>;
}

/** A running regulatory clock: "Quedan 32 h", or "Vencido hace 5 h" once past (console-unification spec). */
export function ClockBadge({ dueAt, className }: { dueAt: string; className?: string }) {
  const t = useTranslations("deadline");
  const c = countdown(dueAt, useNow());
  return <Badge severity={c.past ? "overdue" : "clock"} className={className}>{t(c.past ? "past" : "left", { unit: c.unit, value: c.value })}</Badge>;
}
