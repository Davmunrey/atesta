/** Provenance metadata gate; it does not authenticate a recorded scan. */
import { readFileSync, realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isCalendarDate(value: unknown): boolean {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function landingIssues(value: unknown): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return ["fixture"];
  const fixture = value as Record<string, unknown>;
  const issues: string[] = [];
  if (fixture.origin !== "recorded") issues.push("origin");
  if (typeof fixture.scan_id !== "string" || !UUID.test(fixture.scan_id)) issues.push("scan_id");
  if (!isCalendarDate(fixture.scan_date)) issues.push("scan_date");
  return issues;
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let issues: string[];
  if (process.argv.length > 3) {
    issues = ["expected at most one input file"];
  } else {
    const file = process.argv[2] ?? new URL("../src/content/landing-fixture.json", import.meta.url);
    try {
      issues = landingIssues(JSON.parse(readFileSync(file, "utf8")));
    } catch {
      // JSON parse errors can quote file contents, so only emit a fixed diagnostic.
      issues = ["fixture could not be loaded"];
    }
  }
  if (issues.length > 0) {
    console.error(`check-landing: blocked (${issues.join(", ")})`);
    process.exitCode = 1;
  } else {
    console.log("check-landing: passed (provenance metadata only)");
  }
}
