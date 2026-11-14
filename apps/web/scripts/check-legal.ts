/** Metadata completeness gate; legal review remains a separate release requirement. */
import { realpathSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const FIELDS = ["name", "nif", "address", "registry", "email"] as const;

export function legalIssues(value: unknown): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return ["legalEntity"];
  const entity = value as Record<string, unknown>;
  return FIELDS.filter((field) => {
    const item = entity[field];
    return !Object.hasOwn(entity, field) || typeof item !== "string" || item.trim().length === 0;
  });
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let issues: string[];
  if (process.argv.length > 3) {
    issues = ["expected at most one input file"];
  } else {
    const file = process.argv[2]
      ? pathToFileURL(resolve(process.argv[2]))
      : new URL("../src/content/legal-entity.ts", import.meta.url);
    try {
      const content: { legalEntity?: unknown } = await import(file.href);
      issues = legalIssues(content.legalEntity);
    } catch {
      // Import errors can include input values; never forward their messages.
      issues = ["legalEntity could not be loaded"];
    }
  }
  if (issues.length > 0) {
    console.error(`check-legal: blocked (${issues.join(", ")})`);
    process.exitCode = 1;
  } else {
    console.log("check-legal: passed (metadata only; legal review still required)");
  }
}
