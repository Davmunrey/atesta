// @vitest-environment node
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, it } from "vitest";
import es from "../../messages/es.json";
import en from "../../messages/en.json";
import { evidenceTemplate, isSafeText, type TemplateFormat, USE_CASES, type UseCase } from "@/lib/evidence-templates";

const ORIGIN = "https://atesta.example.test";
const FORMATS: TemplateFormat[] = ["powershell", "bash", "github"];
const texts = (messages: typeof es, useCase: UseCase) => {
  const t = messages.integrations.templates;
  return { title: t.cases[useCase].title, statement: t.cases[useCase].statement, when: t.when[useCase], secret: t.secret };
};

it("every use case and format names its control, reads the token from a secret and retries safely", () => {
  for (const messages of [es, en]) for (const useCase of Object.keys(USE_CASES) as UseCase[]) for (const format of FORMATS) {
    const text = texts(messages, useCase);
    expect(isSafeText(text), `${useCase} text`).toBe(true);
    const script = evidenceTemplate(useCase, format, ORIGIN, text);
    expect(script).toContain(`${ORIGIN}/api/v1/ingest/evidence`);
    expect(script).toContain(USE_CASES[useCase].control);
    expect(script).toContain(USE_CASES[useCase].id);
    expect(script).toMatch(/ATESTA_TOKEN/);
    expect(script).not.toMatch(/atesta_[A-Za-z0-9_-]{20,}/); // never a literal token
    expect(script).toContain(text.statement);
  }
});

it("refuses text that would break the quoting of a script", () => {
  expect(() => evidenceTemplate("backup", "bash", ORIGIN, { title: "x", statement: "a $(rm -rf /)", when: "", secret: "" })).toThrow();
  expect(() => evidenceTemplate("backup", "github", ORIGIN, { title: "it's", statement: "x", when: "", secret: "" })).toThrow();
});

it("the bash template is valid shell", () => {
  const dir = mkdtempSync(join(tmpdir(), "atesta-tpl-"));
  for (const useCase of Object.keys(USE_CASES) as UseCase[]) {
    const bash = join(dir, `${useCase}.sh`);
    writeFileSync(bash, evidenceTemplate(useCase, "bash", ORIGIN, texts(es, useCase)));
    execFileSync("bash", ["-n", bash]);
  }
});
