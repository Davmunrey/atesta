/**
 * Fails on GPL or AGPL licensed packages and on packages with no declared license (ADR-006,
 * web-shell spec). LGPL is allowed: those libraries are used unmodified.
 * Usage: pnpm licenses list --json | node scripts/check-licenses.ts
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

type Entry = { name: string; versions: string[] };
export type Report = Record<string, Entry[]>;

const COPYLEFT = /^A?GPL\b/i;
const UNDECLARED = /^(|UNKNOWN|UNLICENSED|SEE LICENSE.*)$/i;

/**
 * Enough SPDX for this check: an OR expression passes if any branch passes, an AND expression
 * if every part does. Parentheses are dropped; mixed AND/OR lands on the same answer here.
 */
export function isAllowed(expression: string): boolean {
  const bare = expression.replace(/[()]/g, "").trim();
  if (/ OR /i.test(bare)) return bare.split(/ OR /i).some(isAllowed);
  return bare
    .split(/ AND /i)
    .map((id) => id.trim())
    .every((id) => !UNDECLARED.test(id) && !COPYLEFT.test(id));
}

export function violations(report: Report): string[] {
  return Object.entries(report)
    .filter(([license]) => !isAllowed(license))
    .flatMap(([license, entries]) =>
      entries.map((entry) => `${entry.name}@${entry.versions.join(", ")} (${license})`),
    );
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const found = violations(JSON.parse(readFileSync(0, "utf8")) as Report);
  for (const line of found) console.error(`license not allowed: ${line}`);
  process.exit(found.length > 0 ? 1 : 0);
}
