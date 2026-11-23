/**
 * Ready-made scripts that send evidence through the ingestion API (evidence-ingestion-api spec,
 * templates). The token is always read from the environment or a CI secret, never written into the
 * script; the external id makes a retried run write nothing twice.
 */
export const USE_CASES = {
  backup: { control: "ctl.continuity_restore", id: "backup" },
  deployment: { control: "ctl.change_vulnerability_review", id: "deployment" },
  vulnerability_scan: { control: "ctl.change_vulnerability_review", id: "vulnerability-scan" },
  log_review: { control: "ctl.activity_logging_review", id: "log-review" },
} as const;

export type UseCase = keyof typeof USE_CASES;
export type TemplateFormat = "powershell" | "bash" | "github";

export type TemplateText = {
  title: string; // evidence title
  statement: string; // evidence statement
  when: string; // comment: when to run it
  secret: string; // comment: where the token lives
};

// Text goes inside double quotes (PowerShell), an unquoted heredoc (bash) and a single-quoted jq
// filter (GitHub Actions): none of these characters may appear in it.
const UNSAFE = /["'`$\\]/;

export function isSafeText(text: TemplateText): boolean {
  return Object.values(text).every((value) => !UNSAFE.test(value));
}

export function evidenceTemplate(useCase: UseCase, format: TemplateFormat, origin: string, text: TemplateText): string {
  if (!isSafeText(text)) throw new Error("template text has characters that would break the script");
  const { control, id } = USE_CASES[useCase];
  const endpoint = `${origin.replace(/\/$/, "")}/api/v1/ingest/evidence`;
  const title = JSON.stringify(text.title);
  const statement = JSON.stringify(text.statement);
  if (format === "powershell") {
    return [
      `# Atesta: ${text.title}. ${text.when}`,
      `# ${text.secret}`,
      `$ErrorActionPreference = "Stop"`,
      `$body = @{`,
      `  control     = "${control}"`,
      `  title       = ${title}`,
      `  statement   = ${statement}`,
      `  source      = "windows-task"`,
      `  external_id = "${id}-" + (Get-Date -Format "yyyy-MM-dd")`,
      `} | ConvertTo-Json`,
      `Invoke-RestMethod -Method Post -Uri "${endpoint}" \``,
      `  -Headers @{ Authorization = "Bearer $env:ATESTA_TOKEN" } \``,
      `  -ContentType "application/json; charset=utf-8" \``,
      `  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))`,
    ].join("\n");
  }
  if (format === "bash") {
    return [
      `#!/usr/bin/env bash`,
      `# Atesta: ${text.title}. ${text.when}`,
      `# ${text.secret}`,
      `set -euo pipefail`,
      `EXTERNAL_ID="${id}-$(date +%F)"`,
      `curl --fail-with-body -sS -X POST "${endpoint}" \\`,
      `  -H "Authorization: Bearer \${ATESTA_TOKEN:?ATESTA_TOKEN is not set}" \\`,
      `  -H "Content-Type: application/json" \\`,
      `  --data @- <<JSON`,
      `{"control": "${control}", "title": ${title}, "statement": ${statement}, "source": "cron", "external_id": "$EXTERNAL_ID"}`,
      `JSON`,
    ].join("\n");
  }
  return [
    `# Atesta: ${text.title}. ${text.when}`,
    `# ${text.secret}`,
    `- name: Atesta evidence`,
    `  if: success()`,
    `  env:`,
    `    ATESTA_TOKEN: \${{ secrets.ATESTA_TOKEN }}`,
    `  run: |`,
    `    curl --fail-with-body -sS -X POST "${endpoint}" \\`,
    `      -H "Authorization: Bearer \${ATESTA_TOKEN}" \\`,
    `      -H "Content-Type: application/json" \\`,
    `      -d "$(jq -n --arg ref "\${GITHUB_SERVER_URL}/\${GITHUB_REPOSITORY}/actions/runs/\${GITHUB_RUN_ID}" --arg id "${id}-\${GITHUB_RUN_ID}-\${GITHUB_RUN_ATTEMPT}" '{control: "${control}", title: ${title}, statement: ${statement}, source: "github-actions", reference_url: $ref, external_id: $id}')"`,
  ].join("\n");
}
