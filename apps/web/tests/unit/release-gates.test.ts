import { spawnSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Synthetic identity and scan metadata; no customer or company records.
const legal = {
  name: "Synthetic Entity",
  nif: "SYNTHETIC-NIF",
  address: "Synthetic address",
  registry: "Synthetic registry",
  email: "release@example.invalid",
};
const recorded = {
  origin: "recorded",
  scan_id: "00000000-0000-4000-8000-000000000001",
  scan_date: "2024-02-29",
};

let directory: string;
beforeEach(() => {
  directory = mkdtempSync(join(tmpdir(), "atesta-release-"));
  mkdirSync(join(directory, "package/scripts"), { recursive: true });
  mkdirSync(join(directory, "package/src/content"), { recursive: true });
});
afterEach(() => { rmSync(directory, { recursive: true, force: true }); });

function run(gate: "legal" | "landing", source?: string, extra: string[] = []) {
  const original = fileURLToPath(new URL(`../../scripts/check-${gate}.ts`, import.meta.url));
  const script = join(directory, `package/scripts/check-${gate}.ts`);
  copyFileSync(original, script);
  const args = [script];
  if (source !== undefined) {
    const input = join(directory, gate === "legal" ? "entity.mts" : "fixture.json");
    writeFileSync(input, source);
    args.push(input);
  }
  const result = spawnSync(process.execPath, [...args, ...extra], {
    cwd: directory, encoding: "utf8", timeout: 10_000,
  });
  expect(result.error).toBeUndefined();
  expect(result.signal).toBeNull();
  return result;
}

function blocked(result: ReturnType<typeof run>, gate: string) {
  expect(result.status).toBe(1);
  expect(result.stderr).toContain(`check-${gate}: blocked`);
  expect(result.stdout).toBe("");
}

describe("legal release gate", () => {
  it("accepts a complete identity from a different working directory without printing it", () => {
    const result = run("legal", `export const legalEntity = ${JSON.stringify(legal)};`);
    expect(result.status).toBe(0);
    expect(result.stderr).toBe("");
    expect(result.stdout).toContain("check-legal: passed");
    for (const value of Object.values(legal)) expect(result.stdout).not.toContain(value);
  });

  it.each(Object.keys(legal))("blocks a missing %s field", (field) => {
    const incomplete: Record<string, unknown> = { ...legal };
    delete incomplete[field];
    const result = run("legal", `export const legalEntity = ${JSON.stringify(incomplete)};`);
    blocked(result, "legal");
    expect(result.stderr).toContain(field);
    for (const value of Object.values(legal)) expect(result.stderr).not.toContain(value);
  });

  it.each(["", " \n\t", null, 42, false, [], {}])("blocks an invalid field value: %j", (value) => {
    blocked(run("legal", `export const legalEntity = ${JSON.stringify({ ...legal, name: value })};`), "legal");
  });

  it.each(["null", "[]", '"identity"', "42"])("blocks a non-object export: %s", (value) => {
    blocked(run("legal", `export const legalEntity = ${value};`), "legal");
  });

  it.each([
    "export default {};",
    "export const legalEntity = ;",
    'throw new Error("synthetic-private-input");',
  ])("blocks unreadable exports without echoing their contents", (source) => {
    const result = run("legal", source);
    blocked(result, "legal");
    expect(result.stderr).not.toContain("synthetic-private-input");
    expect(result.stderr).not.toContain("SyntaxError");
  });
});

describe("landing release gate", () => {
  it("accepts recorded metadata with a real leap day", () => {
    const result = run("landing", JSON.stringify(recorded));
    expect(result.status).toBe(0);
    expect(result.stderr).toBe("");
    expect(result.stdout).toContain("check-landing: passed");
    expect(result.stdout).not.toContain(recorded.scan_id);
  });

  it.each(["illustrative", "", " recorded ", null, true])("blocks a non-recorded origin: %j", (origin) => {
    blocked(run("landing", JSON.stringify({ ...recorded, origin })), "landing");
  });

  it.each(["origin", "scan_id", "scan_date"])("blocks missing provenance: %s", (field) => {
    const incomplete: Record<string, unknown> = { ...recorded };
    delete incomplete[field];
    const result = run("landing", JSON.stringify(incomplete));
    blocked(result, "landing");
    expect(result.stderr).toContain(field);
  });

  it.each(["", "not-a-scan", 1, null, [], {}])("blocks an invalid scan id: %j", (scan_id) => {
    blocked(run("landing", JSON.stringify({ ...recorded, scan_id })), "landing");
  });

  it.each(["", "2023-02-29", "2024-02-30", "2024-13-01", "2024-00-01", "2024-01-00", "29/02/2024", "2024-02-29T00:00:00Z", 1, null])(
    "blocks an invalid calendar date: %j", (scan_date) => {
      blocked(run("landing", JSON.stringify({ ...recorded, scan_date })), "landing");
    },
  );

  it.each(["null", "[]", '"fixture"', "42", "", '{"private": "synthetic-private-input",}'])(
    "blocks malformed input without echoing it", (source) => {
      const result = run("landing", source);
      blocked(result, "landing");
      expect(result.stderr).not.toContain("synthetic-private-input");
      expect(result.stderr).not.toContain("SyntaxError");
    },
  );
});

describe.each(["legal", "landing"] as const)("%s CLI boundary", (gate) => {
  it("blocks absent default content even when another working directory contains a valid decoy", () => {
    mkdirSync(join(directory, "src/content"), { recursive: true });
    writeFileSync(join(directory, "src/content/legal-entity.ts"), `export const legalEntity = ${JSON.stringify(legal)};`);
    writeFileSync(join(directory, "src/content/landing-fixture.json"), JSON.stringify(recorded));
    blocked(run(gate), gate);
  });

  it("loads default content relative to the script instead of the working directory", () => {
    writeFileSync(join(directory, "package/src/content/legal-entity.ts"), `export const legalEntity = ${JSON.stringify(legal)};`);
    writeFileSync(join(directory, "package/src/content/landing-fixture.json"), JSON.stringify(recorded));
    const result = run(gate);
    expect(result.status).toBe(0);
    expect(result.stderr).toBe("");
  });

  it("blocks a missing explicit file", () => {
    blocked(run(gate, undefined, [join(directory, "missing")]), gate);
  });

  it("rejects extra arguments even when input is complete", () => {
    const source = gate === "legal" ? `export const legalEntity = ${JSON.stringify(legal)};` : JSON.stringify(recorded);
    blocked(run(gate, source, ["--skip"]), gate);
  });
});
