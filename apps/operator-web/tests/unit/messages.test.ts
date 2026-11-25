// @vitest-environment node
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { messageKey } from "@atesta/ui/api-error";
import codes from "../../../operator/contract/error-codes.json";
import { MESSAGES } from "@/lib/messages";
import en from "../../messages/en.json";
import es from "../../messages/es.json";

/** Every portal string in Spanish and English (i18n-complete spec; operator-portal spec, "Strings"). */
function leaves(tree: object, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return value !== null && typeof value === "object" ? leaves(value as object, path) : [[path, String(value)] as [string, string]];
  });
}
function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? sources(path) : path.endsWith(".tsx") ? [path] : [];
  });
}

describe("portal messages", () => {
  it("hold the same keys in Spanish and English, none empty", () => {
    expect(leaves(en).map(([k]) => k).sort()).toEqual(leaves(es).map(([k]) => k).sort());
    for (const [key, text] of [...leaves(es), ...leaves(en)]) expect(text.trim(), key).not.toBe("");
  });

  it("give every operator API error code a text in both languages, and nothing else under errors", () => {
    for (const locale of ["es", "en"] as const) {
      const keys = leaves(MESSAGES[locale].errors).map(([k]) => k).sort();
      expect(keys, locale).toEqual([...codes, "unknown"].sort());
      for (const code of codes) expect(messageKey(code, MESSAGES[locale])).toBe(`errors.${code}`);
    }
  });

  it("take the operator.* texts from the API's contract, never a copy", () => {
    expect(JSON.stringify([es, en])).not.toContain("\"operator\":");
  });

  it("use ICU plurals for counts", () => {
    const counted = [...leaves(es), ...leaves(en)].filter(([, v]) => /\{(count|total|rows|members)\}/.test(v) && !v.includes(", plural,"));
    expect(counted.map(([k]) => k)).toEqual([]);
  });

  it("no component writes user-facing text inline", () => {
    const offenders = sources(join(import.meta.dirname, "../../src")).flatMap((file) => {
      const code = readFileSync(file, "utf8").replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
      const text = [...code.matchAll(/>([^<>{}()?:=&|;`]*[A-Za-zÀ-ÿ]{2,}[^<>{}()?:=&|;`]*)</g)].map((m) => m[1]!.trim());
      const attrs = [...code.matchAll(/\b(aria-label|title|placeholder|alt)="([^"]*[A-Za-zÀ-ÿ]{2,}[^"]*)"/g)].map((m) => m[2]!);
      return [...text, ...attrs].filter(Boolean).map((t) => `${file}: ${t}`);
    });
    expect(offenders).toEqual([]);
  });
});
