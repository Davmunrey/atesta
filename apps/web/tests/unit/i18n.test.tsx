// @vitest-environment jsdom
/** Complete internationalization (i18n-complete spec): guards that keep ES and EN whole. */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { cleanup, screen } from "@testing-library/react";
import { createTranslator } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RequirementGuidance, SourceCoverage } from "@/components/catalog-preparation";
import { FrameworkDetailView } from "@/components/framework-detail";
import { preferredLocale } from "@/i18n/locale";
import { percent } from "@/lib/format";
import en from "../../messages/en.json";
import es from "../../messages/es.json";
import { framework } from "../fixtures/framework";
import { renderWithProviders, stubApi } from "./render";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

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
const SRC = join(__dirname, "../../src");

describe("language choice", () => {
  it("follows the browser on a first visit", () => {
    expect(preferredLocale("", ["en-GB", "es"])).toBe("en");
    expect(preferredLocale("", ["fr-FR", "en-US"])).toBe("en");
    expect(preferredLocale("", ["es-ES", "en"])).toBe("es");
    expect(preferredLocale("", ["de-DE"])).toBe("es");
    expect(preferredLocale("", [])).toBe("es");
  });

  it("an explicit choice always wins", () => {
    expect(preferredLocale("atesta_locale=es", ["en-US"])).toBe("es");
    expect(preferredLocale("atesta_locale=en", ["es-ES"])).toBe("en");
  });
});

describe("messages", () => {
  const COUNTS = /\{(count|total|shown|evaluated|expected|assessed|applies|implemented|partial|notApplicable|days|requirements|controls)\}/;

  it.each([["es", es], ["en", en]] as const)("every counted %s message has plural forms", (_, messages) => {
    const missing = leaves(messages).filter(([, value]) => COUNTS.test(value) && !value.includes(", plural,")).map(([key]) => key);
    expect(missing).toEqual([]);
  });

  it.each([
    ["es", 1, "1 requisito disponible"], ["es", 2, "2 requisitos disponibles"],
    ["en", 1, "1 available requirement"], ["en", 2, "2 available requirements"],
  ] as const)("%s: %d requirements", (locale, count, text) => {
    const t = createTranslator({ locale, messages: locale === "es" ? es : en });
    expect(t("preparation.requirementsCount", { count })).toBe(text);
  });

  it("the breakdown reads naturally for one", () => {
    const t = createTranslator({ locale: "es", messages: es });
    expect(t("register.breakdown", { applies: 1, implemented: 1, partial: 0, notApplicable: 1 }))
      .toBe("Aplica 1: 1 implantada y 0 parcialmente. No aplica 1.");
  });

  it("no component writes user-facing text inline", () => {
    const offenders = sources(SRC).flatMap((file) => {
      const code = readFileSync(file, "utf8").replace(/\{\/\*[\s\S]*?\*\/\}/g, "");
      const text = [...code.matchAll(/>([^<>{}()?:=&|;`]*[A-Za-zÀ-ÿ]{2,}[^<>{}()?:=&|;`]*)</g)].map((m) => m[1]!.trim());
      const attrs = [...code.matchAll(/\b(aria-label|title|placeholder|alt)="([^"]*[A-Za-zÀ-ÿ]{2,}[^"]*)"/g)].map((m) => m[2]!);
      return [...text, ...attrs].filter(Boolean).map((t) => `${file.replace(SRC, "src")}: ${t}`);
    });
    expect(offenders).toEqual([]);
  });

  it("percentages come from the locale, never from a hand-written sign", () => {
    // A number shown as a percentage, built by hand; CSS lengths (`${x}%` in style) are not text.
    const offenders = sources(SRC).filter((file) => /\} %`|format\.number\([^`]*\)\}%/.test(readFileSync(file, "utf8")));
    expect(offenders).toEqual([]);
  });
});

describe("formats", () => {
  it("formats a score in each locale's percent style", () => {
    expect(percent("es", 45.25)).toBe("45,3\u00a0%"); // Intl keeps the sign on the number's line
    expect(percent("en", 45.25)).toBe("45.3%");
    expect(percent("en", 100)).toBe("100%");
  });
});

describe("official Spanish text in the English interface", () => {
  it("marks fallback titles as Spanish and says once that they are official", async () => {
    stubApi({ "GET /api/v1/orgs/primary/frameworks/synthetic_alpha": [200, {
      ...framework, requirements: framework.requirements.map((r) => ({ ...r, title_en: null })),
    }] });
    renderWithProviders(<FrameworkDetailView orgId="primary" frameworkKey="synthetic_alpha" />, "en");
    const title = await screen.findByText(framework.requirements[0]!.title_es!);
    expect(title.closest("[lang]")?.getAttribute("lang")).toBe("es");
    expect(screen.getAllByText(/official Spanish text/)).toHaveLength(1);
  });
});

describe("official text in both languages (content model v2)", () => {
  const eu = { official_text_es: "Texto oficial en español.", official_text_en: "Official English text.", section: "Artículo 21", source_sha256: "b".repeat(64) };

  it.each([["es", "Texto oficial en español.", "es"], ["en", "Official English text.", "en"]] as const)(
    "%s interface shows the official text in its own language", async (locale, text, lang) => {
      stubApi({});
      renderWithProviders(<RequirementGuidance guidance={eu} />, locale);
      expect(screen.getByText(text).getAttribute("lang")).toBe(lang);
      expect(screen.queryByRole("table")).toBeNull(); // no selection table without selection rules
    });

  it("falls back to the Spanish text, marked as such, when no official English exists", () => {
    stubApi({});
    renderWithProviders(<RequirementGuidance guidance={{ ...eu, official_text_en: null }} />, "en");
    expect(screen.getByText("Texto oficial en español.").getAttribute("lang")).toBe("es");
  });

  it("lists every unit of the source, imported or excluded with its reason", () => {
    stubApi({});
    renderWithProviders(<SourceCoverage coverage={{ source: "Synthetic act", entries: [
      { units: ["art20", "art21.1-4"], status: "covered", requirements: ["a", "b", "c"] },
      { units: ["art1", "annex3", "da2", "dt"], status: "excluded", reason_es: "Motivo sintético.", reason_en: "Synthetic reason." },
    ] }} />, "en");
    expect(screen.getByText("2 parts imported as requirements and 4 excluded with their reasons.")).toBeTruthy();
    expect(screen.getByText("Art. 20, Art. 21.1-4")).toBeTruthy();
    expect(screen.getByText("imported: 3 requirements")).toBeTruthy();
    expect(screen.getByText("Art. 1, Annex III, Additional provision 2, Transitional provision")).toBeTruthy();
    expect(screen.getByText("Synthetic reason.")).toBeTruthy();
  });
});
