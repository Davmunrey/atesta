import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

// One design system, never copied components (ADR-017; ui-package spec).
const REPO = join(import.meta.dirname, "../../../..");
const WEB = join(REPO, "apps/web");
const UI = join(REPO, "packages/ui");
const pkg = JSON.parse(readFileSync(join(UI, "package.json"), "utf8")) as {
  name: string; exports: Record<string, string>; peerDependencies: Record<string, string>;
};

function files(dir: string, pattern = /\.(ts|tsx|mjs)$/): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (["node_modules", ".next", "out"].includes(entry.name)) return [];
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path, pattern) : pattern.test(entry.name) ? [path] : [];
  });
}

const DECLARED = /^export (?:default )?(?:async )?(?:function\*?|const|let|class|type|interface|enum) (\w+)/gm;
const declared = (file: string) => [...readFileSync(file, "utf8").matchAll(DECLARED)].map((m) => m[1]!);
const SPECIFIER = /(?:from\s+|import\s*\(\s*|vi\.mock\(\s*|@import\s+)["']([^"']+)["']/g;
const specifiers = (file: string) => [...readFileSync(file, "utf8").matchAll(SPECIFIER)].map((m) => m[1]!);

/** Every selector of every style rule in a stylesheet (at-rule preludes skipped), whitespace normalised. */
function selectors(css: string): string[] {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const found: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "{") {
      const prelude = text.slice(start, i).trim();
      if (prelude && !prelude.startsWith("@")) {
        let depth = 0, part = "";
        for (const ch of prelude) {
          if (ch === "(") depth++;
          if (ch === ")") depth--;
          if (ch === "," && depth === 0) { found.push(part.trim().replace(/\s+/g, " ")); part = ""; } else part += ch;
        }
        found.push(part.trim().replace(/\s+/g, " "));
      }
      start = i + 1;
    } else if (text[i] === "}" || text[i] === ";") start = i + 1;
  }
  return found.filter(Boolean);
}
const classes = (selector: string) => [...selector.replace(/\[[^\]]*\]/g, "").matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)].map((m) => m[1]!);

const uiFiles = files(UI);
const webFiles = [...files(join(WEB, "src"), /\.(ts|tsx|css)$/), ...files(join(WEB, "tests")), ...files(join(WEB, "scripts")),
  ...readdirSync(WEB).filter((name) => /\.(ts|mjs)$/.test(name)).map((name) => join(WEB, name))];

describe("the shared UI package", () => {
  it("is the only place its exports are defined", () => {
    const shared = new Set(uiFiles.flatMap(declared));
    expect(shared.size).toBeGreaterThan(20);
    const copies = webFiles.filter((file) => /\.tsx?$/.test(file)).flatMap((file) =>
      declared(file).filter((name) => shared.has(name)).map((name) => `${relative(WEB, file)}: ${name}`));
    expect(copies).toEqual([]);
  });

  it("is imported by the app only through its name, never by path", () => {
    const byPath = webFiles.flatMap((file) => specifiers(file)
      .filter((spec) => spec.includes("packages/ui") || (spec.startsWith(".") && resolve(dirname(file), spec).startsWith(UI)))
      .map((spec) => `${relative(WEB, file)}: ${spec}`));
    expect(byPath).toEqual([]);
  });

  it("is imported through entries it exports", () => {
    const entries = Object.keys(pkg.exports).map((key) => key.replace(/^\./, pkg.name));
    const exported = (spec: string) => entries.some((entry) => entry.endsWith("*") ? spec.startsWith(entry.slice(0, -1)) : spec === entry);
    const used = webFiles.flatMap(specifiers).filter((spec) => spec.startsWith(`${pkg.name}/`));
    expect(used.length).toBeGreaterThan(50);
    expect(used.filter((spec) => !exported(spec))).toEqual([]);
    for (const target of Object.values(pkg.exports).filter((path) => !path.includes("*"))) {
      expect(existsSync(join(UI, target)), target).toBe(true);
    }
  });

  it("never reaches into an app", () => {
    const allowed = (spec: string) => spec.startsWith("node:") || spec.startsWith("./") || spec.startsWith("../")
      || Object.keys(pkg.peerDependencies).some((dep) => spec === dep || spec.startsWith(`${dep}/`));
    const reaching = [...uiFiles, ...files(join(UI, "src"), /\.css$/)].flatMap((file) => specifiers(file)
      .filter((spec) => !allowed(spec) || (spec.startsWith(".") && !resolve(dirname(file), spec).startsWith(UI)))
      .map((spec) => `${relative(UI, file)}: ${spec}`));
    expect(reaching).toEqual([]);
  });

  it("holds the shared component styles; the app only adds rules in its own context", () => {
    const shared = readFileSync(join(UI, "src/styles/components.css"), "utf8");
    const owned = new Set(selectors(shared).flatMap(classes));
    expect([...owned]).toEqual(expect.arrayContaining(["dashboard-button", "button-primary", "button-danger", "field", "page-header",
      "breadcrumbs", "panel", "badge", "table-region", "state-loading", "state-error", "state-empty",
      // The app shell (#486): every signed-in app draws the same frame.
      "console", "topbar", "topbar-brand", "sidenav", "console-page", "notice", "account-menu", "skip-link", "brand-seal",
      "confirm-row", "form-actions"]));
    const sharedSelectors = new Set(selectors(shared));
    const app = files(join(WEB, "src"), /\.css$/);
    const defined = app.flatMap((file) => selectors(readFileSync(file, "utf8"))
      // A rule that names only package classes (or repeats a package selector) defines the component in the app.
      .filter((sel) => sharedSelectors.has(sel) || (classes(sel).length > 0 && classes(sel).every((name) => owned.has(name))))
      .map((sel) => `${relative(WEB, file)}: ${sel}`));
    expect(defined).toEqual([]);
    const globals = readFileSync(join(WEB, "src/app/globals.css"), "utf8");
    // Imported before the app's stylesheets, so an app rule of the same specificity wins.
    expect(globals.indexOf(`@import "${pkg.name}/styles/components.css";`)).toBeGreaterThan(-1);
    expect(globals.indexOf(`@import "${pkg.name}/styles/components.css";`)).toBeLessThan(globals.indexOf('@import "../styles/'));
  });

  it("is declared as a workspace dependency of the app", () => {
    const web = JSON.parse(readFileSync(join(WEB, "package.json"), "utf8")) as { dependencies: Record<string, string> };
    expect(web.dependencies[pkg.name]).toBe("workspace:*");
  });
});

describe("one pnpm workspace at the repository root", () => {
  const workspace = readFileSync(join(REPO, "pnpm-workspace.yaml"), "utf8");

  it("lists the apps and the package, with the supply-chain settings", () => {
    expect(workspace).toMatch(/^packages:\n {2}- apps\/web\n {2}- apps\/operator-web\n {2}- packages\/ui\n/m);
    expect(workspace).toMatch(/^minimumReleaseAge: 10080$/m);
    expect(workspace).toMatch(/^blockExoticSubdeps: true$/m);
    expect(workspace).toMatch(/^trustPolicy: no-downgrade$/m);
  });

  it("has one lockfile, at the root", () => {
    expect(existsSync(join(REPO, "pnpm-lock.yaml"))).toBe(true);
    expect(existsSync(join(WEB, "pnpm-lock.yaml"))).toBe(false);
    expect(existsSync(join(WEB, "pnpm-workspace.yaml"))).toBe(false);
  });
});
