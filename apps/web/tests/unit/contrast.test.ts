import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const [css = "", print = ""] = readFileSync(join(import.meta.dirname, "../../src/styles/tokens.css"), "utf8").split("@media print");
const [workspace = "", publicLight = ""] = css.split(".public-surface");
const [light = "", dark = ""] = workspace.split("prefers-color-scheme: dark");

function palette(block: string): Map<string, string> {
  return new Map([...block.matchAll(/--color-([a-z-]+):\s*(#[0-9a-f]{6});/gi)].map((m) => [m[1]!, m[2]!]));
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

// WCAG 2.1 AA: 4.5:1 for text, 3:1 for focus indicators and borders of controls.
const TEXT: [string, string][] = [
  ["fg", "bg"], ["fg", "surface"], ["muted", "bg"], ["muted", "surface"], ["link", "bg"],
  ["accent-fg", "accent"], ["danger", "bg"], ["danger-fg", "danger"],
  ["success", "bg"], ["success", "surface"], ["warning", "bg"], ["warning", "surface"], ["danger", "surface"],
];
const NON_TEXT: [string, string][] = [["focus", "bg"], ["focus", "surface"], ["border", "bg"]];

describe.each([["light", light], ["dark", dark], ["public", publicLight]])("%s theme", (_, block) => {
  const colors = palette(block);
  it.each(TEXT)("%s on %s is at least 4.5:1", (fg, bg) => {
    expect(ratio(colors.get(fg)!, colors.get(bg)!)).toBeGreaterThanOrEqual(4.5);
  });
  it.each(NON_TEXT)("%s on %s is at least 3:1", (fg, bg) => {
    expect(ratio(colors.get(fg)!, colors.get(bg)!)).toBeGreaterThanOrEqual(3);
  });
});

// Console panels (ui-polish spec): text reads on the panel, and the surface level (header rows,
// hover, inline forms) stays distinct from the panel in both themes.
describe.each([["light", light], ["dark", dark]])("%s console", (_, block) => {
  const colors = palette(block);
  it.each([["fg", "panel"], ["muted", "panel"], ["link", "panel"], ["success", "panel"], ["warning", "panel"], ["danger", "panel"], ["link", "surface"]])(
    "%s on %s is at least 4.5:1",
    (fg, bg) => expect(ratio(colors.get(fg)!, colors.get(bg)!)).toBeGreaterThanOrEqual(4.5),
  );
  it("keeps surface and panel apart", () => {
    expect(ratio(colors.get("surface")!, colors.get("panel")!)).toBeGreaterThanOrEqual(1.05);
  });
});

// Paper: print uses the light palette on white, so text keeps its contrast on any screen theme.
describe("print", () => {
  const colors = palette(print);
  it.each([["fg", "bg"], ["muted", "bg"], ["link", "bg"], ["danger", "bg"], ["success", "bg"], ["warning", "bg"], ["muted", "surface"]])(
    "%s on %s is at least 4.5:1",
    (fg, bg) => expect(ratio(colors.get(fg)!, colors.get(bg)!)).toBeGreaterThanOrEqual(4.5),
  );
  it("prints on white", () => expect([colors.get("bg"), colors.get("page"), colors.get("panel")]).toEqual(["#ffffff", "#ffffff", "#ffffff"]));
});

// Landing (landing-legal L4): the closing band is ink, with paper text and the yellow CTA.
describe("landing ink band", () => {
  const colors = palette(publicLight);
  it.each([["on-ink", "ink"], ["on-ink-muted", "ink"], ["ink", "cta"]])("%s on %s is at least 4.5:1", (fg, bg) => {
    expect(ratio(colors.get(fg)!, colors.get(bg)!)).toBeGreaterThanOrEqual(4.5);
  });
});
