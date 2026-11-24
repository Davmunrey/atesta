/**
 * Build step (landing-legal spec, security.txt): writes out/.well-known/security.txt, the
 * RFC 9116 file that tells a researcher where to report a vulnerability. It is generated, not
 * kept in public/, because RFC 9116 section 2.5.5 requires an Expires date and a hand-kept date
 * goes stale: every build moves it forward, and a deployment older than MAX_AGE_DAYS shows it.
 * Usage: node scripts/security-txt.ts (after next build).
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

/** Days the file stays valid after a build. RFC 9116 section 2.5.5 recommends less than a year. */
export const MAX_AGE_DAYS = 180;

/** Section 2.5.3: listed in order of preference. The mailbox comes first (owner, 2026-11-24). */
const CONTACTS = [
  "mailto:security@atesta.cloud",
  "https://github.com/Davmunrey/atesta/security/advisories/new",
];
/** Section 2.5.2: every URI the file is served from. The site and the app share one export. */
const CANONICAL = [
  "https://atesta.cloud/.well-known/security.txt",
  "https://app.atesta.cloud/.well-known/security.txt",
];
const POLICY = "https://github.com/Davmunrey/atesta/blob/main/SECURITY.md";
const DAY_MS = 86_400_000;
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/i;

export function securityTxt(now: Date): string {
  const expires = new Date(now.getTime() + MAX_AGE_DAYS * DAY_MS).toISOString().replace(/\.\d{3}Z$/, "Z");
  return [
    "# Atesta: how to report a security vulnerability (RFC 9116).",
    ...CONTACTS.map((contact) => `Contact: ${contact}`),
    `Expires: ${expires}`,
    "Preferred-Languages: es, en",
    ...CANONICAL.map((uri) => `Canonical: ${uri}`),
    `Policy: ${POLICY}`,
    "",
  ].join("\n");
}

/** The `Name: value` lines, in order. Comments (#) and blank lines are skipped. */
export function parse(text: string): [string, string][] {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim() !== "" && !line.startsWith("#"))
    .map((line): [string, string] => {
      const colon = line.indexOf(":");
      return [line.slice(0, colon).trim(), line.slice(colon + 1).trim()];
    });
}

/** What RFC 9116 forbids in `text`; empty when the file may be published. */
export function problems(text: string, now: Date): string[] {
  const fields = parse(text);
  const values = (name: string) => fields.filter(([field]) => field === name).map(([, value]) => value);
  const found: string[] = [];
  const contacts = values("Contact");
  if (contacts.length === 0) found.push("Contact is required");
  if (contacts.some((contact) => !/^(mailto:|tel:|https:\/\/)/.test(contact))) {
    found.push("Contact must be a mailto:, tel: or https: URI");
  }
  for (const name of ["Canonical", "Policy"]) {
    if (values(name).some((uri) => !uri.startsWith("https://"))) found.push(`${name} must be https`);
  }
  const expires = values("Expires");
  if (expires.length !== 1) {
    found.push("Expires must appear exactly once");
  } else if (!RFC3339.test(expires[0]!) || Number.isNaN(Date.parse(expires[0]!))) {
    found.push("Expires is not RFC 3339");
  } else {
    const left = Date.parse(expires[0]!) - now.getTime();
    if (left <= 0) found.push("Expires is in the past");
    if (left >= 365 * DAY_MS) found.push("Expires is a year or more ahead");
  }
  if (values("Preferred-Languages").length > 1) found.push("Preferred-Languages must not appear more than once");
  return found;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const now = new Date();
  const text = securityTxt(now);
  const found = problems(text, now);
  if (found.length > 0) throw new Error(`security.txt breaks RFC 9116: ${found.join("; ")}`);
  const dir = join(fileURLToPath(new URL("..", import.meta.url)), "out", ".well-known");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "security.txt"), text);
  console.log(`security.txt: valid for ${MAX_AGE_DAYS} days`);
}
