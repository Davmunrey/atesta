import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The owner's rule for the portal ("que la app no sea un frankenstein"; ADR-017, "Design system"):
 * every screen is built only from @atesta/ui tokens and components. A component the portal needs
 * goes into packages/ui and DESIGN.md, never into this app.
 */
const APP = join(import.meta.dirname, "../..");
const REPO = join(APP, "../..");
const UI = join(REPO, "packages/ui");
const pkg = JSON.parse(readFileSync(join(UI, "package.json"), "utf8")) as { name: string; exports: Record<string, string> };

function files(dir: string, pattern = /\.(ts|tsx|mjs|css)$/): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (["node_modules", ".next", "out", "test-results"].includes(entry.name)) return [];
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path, pattern) : pattern.test(entry.name) ? [path] : [];
  });
}
const source = files(join(APP, "src"));
const everything = [...source, ...files(join(APP, "tests")), ...files(join(APP, "scripts"))];
const DECLARED = /^export (?:default )?(?:async )?(?:function\*?|const|let|class|type|interface|enum) (\w+)/gm;
const declared = (file: string) => [...readFileSync(file, "utf8").matchAll(DECLARED)].map((m) => m[1]!);
const SPECIFIER = /(?:from\s+|import\s*\(\s*|vi\.mock\(\s*|@import\s+)["']([^"']+)["']/g;
const specifiers = (file: string) => [...readFileSync(file, "utf8").matchAll(SPECIFIER)].map((m) => m[1]!);

/** What the design-system rule refuses in a source file. */
function designViolations(text: string, css: boolean): string[] {
  const found: string[] = [];
  if (css) {
    // Only imports and comments: no rule, custom property or value of the app's own.
    const rest = text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^@import\s+"[^"]+";\s*$/gm, "").trim();
    if (rest) found.push(`stylesheet content: ${rest.slice(0, 60)}`);
    return found;
  }
  if (/#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\(/i.test(text)) found.push("colour literal");
  if (/\b[\w-]+-\[[^\]]+\]/.test(text)) found.push("arbitrary Tailwind value");
  if (/\bstyle=\{/.test(text)) found.push("inline style");
  if (/--[a-z][\w-]*\s*:/.test(text)) found.push("custom property");
  if (/<style[\s>]/.test(text)) found.push("style element");
  return found;
}

describe("the portal holds no design of its own", () => {
  it("has one stylesheet, which only imports the shared one", () => {
    const sheets = source.filter((file) => file.endsWith(".css"));
    expect(sheets.map((file) => relative(APP, file))).toEqual(["src/app/globals.css"]);
    const globals = readFileSync(sheets[0]!, "utf8");
    expect(designViolations(globals, true)).toEqual([]);
    for (const entry of ["tokens.css", "components.css", "base.css"]) expect(globals).toContain(`@import "${pkg.name}/styles/${entry}";`);
  });

  it("has no colour, arbitrary value, inline style or custom property in its components", () => {
    const found = source.filter((file) => /\.tsx?$/.test(file)).flatMap((file) =>
      designViolations(readFileSync(file, "utf8"), false).map((v) => `${relative(APP, file)}: ${v}`));
    expect(found).toEqual([]);
  });

  it("refuses each of them when planted", () => {
    expect(designViolations("body { color: red; }", true)).toHaveLength(1);
    expect(designViolations(':root { --brand: 1; }\n@import "x";', true)).toHaveLength(1);
    for (const planted of ['<p className="text-[#ff0000]" />', "<p style={{ margin: 3 }} />", 'const c = "#fafafa";',
      "const s = `--gap: 2px`;", '<p className="p-[13px]" />', "<style>{css}</style>"]) {
      expect(designViolations(planted, false), planted).not.toEqual([]);
    }
  });

  it("never defines a name @atesta/ui exports", () => {
    const shared = new Set(files(UI, /\.(ts|tsx|mjs)$/).flatMap(declared));
    expect(shared.size).toBeGreaterThan(20);
    const copies = everything.filter((file) => /\.tsx?$/.test(file)).flatMap((file) =>
      declared(file).filter((name) => shared.has(name)).map((name) => `${relative(APP, file)}: ${name}`));
    expect(copies).toEqual([]);
  });

  it("imports @atesta/ui through its entries, never by path, and never the console", () => {
    const entries = Object.keys(pkg.exports).map((key) => key.replace(/^\./, pkg.name));
    const exported = (spec: string) => entries.some((entry) => entry.endsWith("*") ? spec.startsWith(entry.slice(0, -1)) : spec === entry);
    const all = everything.flatMap((file) => specifiers(file).map((spec) => ({ file, spec })));
    expect(all.filter(({ spec }) => spec.startsWith(`${pkg.name}/`) && !exported(spec)).map(({ spec }) => spec)).toEqual([]);
    const reaching = all.filter(({ file, spec }) => spec.includes("packages/ui") || spec.includes("apps/web") || spec.startsWith("@atesta/web")
      || (spec.startsWith(".") && [UI, join(REPO, "apps/web")].some((root) => resolve(dirname(file), spec).startsWith(root))));
    expect(reaching.map(({ file, spec }) => `${relative(APP, file)}: ${spec}`)).toEqual([]);
  });

  it("is a workspace member that takes @atesta/ui from the workspace", () => {
    const app = JSON.parse(readFileSync(join(APP, "package.json"), "utf8")) as { dependencies: Record<string, string> };
    expect(app.dependencies[pkg.name]).toBe("workspace:*");
    expect(readFileSync(join(REPO, "pnpm-workspace.yaml"), "utf8")).toMatch(/^ {2}- apps\/operator-web$/m);
  });
});
