import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";
import { expect, it } from "vitest";

const SRC = join(import.meta.dirname, "../../src");
// The shared UI package (ADR-017) holds the tokens and is held to the same rule.
const UI = join(import.meta.dirname, "../../../../packages/ui/src");
const TOKENS = join(UI, "styles/tokens.css");
const COLOR = /#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|color)\(/i;
const ARBITRARY = /\b(?:bg|text|border|ring|fill|stroke|from|to|via|shadow|outline)-\[/;

function files(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? files(join(dir, entry.name)) : [join(dir, entry.name)],
  );
}

it("no color value outside the tokens file", () => {
  const offenders = [SRC, UI].flatMap(files)
    .filter((file) => file !== TOKENS && /\.(tsx?|css)$/.test(file))
    .filter((file) => {
      const text = readFileSync(file, "utf8");
      return COLOR.test(text) || ARBITRARY.test(text);
    })
    .map((file) => relative(join(SRC, ".."), file));
  expect(offenders).toEqual([]);
});

it("the tokens file defines every token group, light and dark", () => {
  const css = readFileSync(TOKENS, "utf8");
  for (const name of ["--color-bg", "--color-fg", "--color-accent", "--color-danger", "--font-sans", "--radius", "--spacing"]) {
    expect(css, name).toContain(`${name}`);
  }
  expect(css).toContain("prefers-color-scheme: dark");
});

it("Tailwind's default palette, fonts and radii are removed", () => {
  const css = readFileSync(TOKENS, "utf8");
  for (const reset of ["--color-*: initial", "--font-*: initial", "--radius-*: initial"]) {
    expect(css).toContain(reset);
  }
});
