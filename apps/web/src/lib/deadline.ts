/**
 * Countdown to a regulatory deadline (console-unification spec, urgency). It only reads the
 * deadline the API computed; it never computes one. Hours below 72 h, days from there. Time left
 * rounds up, so it is never understated; time past rounds down, at least 1.
 */
export type Countdown = { past: boolean; unit: "hours" | "days"; value: number };

const HOUR = 3_600_000;

export function countdown(dueAt: string, now: Date): Countdown {
  const ms = new Date(dueAt).getTime() - now.getTime();
  const past = ms <= 0;
  const hours = past ? Math.max(1, Math.floor(-ms / HOUR)) : Math.ceil(ms / HOUR);
  if (hours < 72) return { past, unit: "hours", value: hours };
  return { past, unit: "days", value: past ? Math.floor(hours / 24) : Math.ceil(ms / (24 * HOUR)) };
}
