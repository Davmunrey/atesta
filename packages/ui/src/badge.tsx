"use client";

import { useNow, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { countdown } from "./deadline";
import { type Severity, type State, STATE_SEVERITY } from "./severity";
import { Icon } from "./icons";

export type { Severity } from "./severity";
const ICON: Record<Severity, string> = { clock: "pending", overdue: "overdue", missing: "missing", pending: "pending", done: "done" };

/** A state written as icon plus text; colour reinforces, never carries it. Name the `state`
 *  (lib/severity.ts); a raw `severity` is for lists that already rank by it (the home's tasks). */
export function Badge({ state, severity, children, className }: { state?: State; severity?: Severity; children: ReactNode; className?: string }) {
  const level = severity ?? STATE_SEVERITY[state ?? "recordsEmpty"];
  return <span className={`badge${className ? ` ${className}` : ""}`} data-severity={level}><Icon name={ICON[level]} />{children}</span>;
}

/** A running regulatory clock: "Quedan 32 h", or "Vencido hace 5 h" once past (console-unification spec). */
export function ClockBadge({ dueAt, className }: { dueAt: string; className?: string }) {
  const t = useTranslations("deadline");
  const c = countdown(dueAt, useNow());
  return <Badge state={c.past ? "clockOverdue" : "clockRunning"} className={className}>{t(c.past ? "past" : "left", { unit: c.unit, value: c.value })}</Badge>;
}
