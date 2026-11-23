/** Assistant engine (assistant spec): normalisation, scoring, golden queries, citations, budget. */
import { cpSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { BUDGET_BYTES, buildIndex, gzippedSize } from "../../scripts/assistant-index";
import { fold, queryTerms, stem, synonymTable, tokens } from "@/lib/assistant/normalize";
import { createEngine, search } from "@/lib/assistant/search";
import type { Doc } from "@/lib/assistant/types";
import faq from "@/content/assistant-faq.json";
import synonyms from "@/content/assistant-synonyms.json";

const CATALOG = join(import.meta.dirname, "../../../../catalog");
const index = buildIndex(CATALOG, faq);
const table = synonymTable(synonyms);
const engine = createEngine(index.docs, table);

describe("normalisation", () => {
  it("folds case and accents", () => {
    expect(fold("Categoría ÁLTA Señal")).toBe("categoria alta senal");
  });

  it.each(["op.acc.6", "OP.ACC.6", "op acc 6", "op-acc-6", "opacc6", "Op.Acc.06"])("reads %s as the code op.acc.6", (spelling) => {
    expect(tokens(spelling)).toEqual(["op.acc.6"]);
  });

  it("reads org, mp and one-letter groups", () => {
    expect(tokens("org 1, mp.s.3 y mp.si.4")).toEqual(["org.1", "mp.s.3", "mp.si.4"]);
  });

  it("does not take ordinary words for codes", () => {
    expect(tokens("opción 2 para la operación")).toEqual(["opcion", "2", "operacion"]);
  });

  it("joins singular and plural, ES and EN", () => {
    expect(stem("incidentes")).toBe(stem("incidente"));
    expect(stem("copias")).toBe(stem("copia"));
    expect(stem("categorías")).toBe(stem("categoría"));
    expect(stem("policies")).toBe(stem("policy"));
    expect(stem("backups")).toBe(stem("backup"));
    expect(stem("24")).toBe("24");
  });

  it("drops stop words in both languages", () => {
    expect(tokens("¿Qué es la política de seguridad?")).toEqual(["politic", "seguridad"]);
    expect(tokens("What is the security policy?")).toEqual(["security", "policy"]);
  });

  it("joins a synonym phrase into one term with every phrase of its group", () => {
    const [term] = queryTerms("backup", table);
    expect(term?.alternatives).toContainEqual(["copi", "seguridad"]);
    expect(queryTerms("copias de seguridad", table)).toHaveLength(1);
  });
});

describe("scoring", () => {
  const doc = (id: string, title: string, text: string, code: string | null = null): Doc => ({
    id, kind: "requirement", framework: "x", code, title: { es: title, en: null }, text: { es: text, en: null }, items: [], keywords: [], cite: [],
  });
  const small = createEngine([
    doc("a", "Copias de seguridad", "Se harán copias de seguridad.", "mp.info.6"),
    doc("b", "Mecanismo de autenticación", "Copias de mp.info.6 y otras cosas.", "op.acc.6"),
    doc("c", "Otra medida", "Texto sobre seguridad y copias de documentos en papel."),
    ...Array.from({ length: 20 }, (_, n) => doc(`filler${n}`, `Medida ${n}`, "Texto de relleno sobre la organización.")),
  ], table);

  it("ranks an exact code match first, even over a text mention", () => {
    expect(search(small, "op.acc.6")[0]?.doc.id).toBe("b");
    expect(search(small, "mp info 6")[0]?.doc.id).toBe("a");
  });

  it("weights the title above the text", () => {
    expect(search(small, "copias de seguridad")[0]?.doc.id).toBe("a");
  });

  it("returns nothing below the threshold", () => {
    expect(search(small, "xyzzy quux")).toEqual([]);
    expect(search(small, "")).toEqual([]);
    expect(search(small, "de la el")).toEqual([]);
  });
});

describe("golden queries on the real catalog", () => {
  const first = (query: string) => search(engine, query)[0]?.doc;

  it("op.acc.6 opens the measure", () => {
    expect(first("op.acc.6")).toMatchObject({ framework: "ens_rd311_2022", code: "op.acc.6" });
  });

  it("copias de seguridad finds mp.info.6", () => {
    expect(first("copias de seguridad")).toMatchObject({ framework: "ens_rd311_2022", code: "mp.info.6" });
    expect(first("backup")).toMatchObject({ code: "mp.info.6" });
  });

  it("plazo NIS2 24 horas finds the early warning, Article 23(4)(a)", () => {
    expect(first("plazo NIS2 24 horas")).toMatchObject({ framework: "nis2", code: "art23.4a" });
  });

  it("categoría MEDIA finds the CCN-STIC 803 rule on categories", () => {
    const hit = first("categoría MEDIA");
    expect(hit?.kind).toBe("valuation");
    expect(hit?.cite[0]).toMatchObject({ kind: "guide", guide: "CCN-STIC 803", section: "4.1" });
  });

  it("evidencias op.exp.2 brings the signed 808 evidence card", () => {
    const hits = search(engine, "evidencias op.exp.2").map((hit) => `${hit.doc.code}:${hit.doc.kind}`);
    expect(hits.slice(0, 2)).toContain("op.exp.2:evidence");
  });

  it("perfil esencial 890C finds the profiles", () => {
    expect(first("perfil esencial 890C")?.kind).toBe("profile");
  });

  it("¿Qué cubre Atesta? finds the product FAQ", () => {
    expect(first("¿Qué cubre Atesta?")?.kind).toBe("faq");
  });

  it("an English question finds the FAQ", () => {
    expect(first("does Atesta certify the ENS")).toMatchObject({ kind: "faq", id: "faq:certify" });
  });

  it("nonsense gets no answer", () => {
    expect(search(engine, "receta de paella valenciana")).toEqual([]);
    expect(search(engine, "zzzz qqqq")).toEqual([]);
  });
});

describe("the index", () => {
  it("cites every document and every item", () => {
    for (const doc of index.docs) {
      expect(doc.cite.length, doc.id).toBeGreaterThan(0);
      for (const item of doc.items) expect(item.cite, doc.id).toBeTruthy();
    }
  });

  it("quotes official text verbatim with an https source", () => {
    const yaml = readFileSync(join(CATALOG, "frameworks/ens_rd311_2022/requirements.yaml"), "utf8");
    const doc = index.docs.find((d) => d.id === "ens_rd311_2022:op.acc.6");
    expect(doc?.text.es).toBeTruthy();
    expect(yaml.replace(/\n {6}/g, "\n")).toContain((doc?.text.es ?? "").split("\n")[0]);
    for (const d of index.docs) for (const c of d.cite) if (c.kind === "official") expect(c.url).toMatch(/^https:\/\//);
  });

  it("keeps only signed CCN-STIC content", () => {
    expect(index.docs.some((d) => d.kind === "evidence")).toBe(true);
    expect(index.flows.valuation?.steps).toHaveLength(5);
    expect(index.flows.profiles?.profiles.map((p) => p.key)).toEqual(["pce_rfs_small_it", "pce_rfs_small_it_ot_iot"]);
    expect(JSON.stringify(index)).not.toMatch(/reviewed_by|"ctl\./); // no signatures, no mappings
    const copy = mkdtempSync(join(tmpdir(), "assistant-catalog-"));
    cpSync(CATALOG, copy, { recursive: true });
    for (const file of ["pack.yaml", "requirements.yaml"]) {
      const path = join(copy, "frameworks/ens_rd311_2022", file);
      writeFileSync(path, readFileSync(path, "utf8").replace(/reviewed_by: .+/g, "reviewed_by: null"));
    }
    const unsigned = buildIndex(copy, faq);
    expect(unsigned.docs.filter((d) => ["evidence", "valuation", "profile"].includes(d.kind))).toEqual([]);
    expect(unsigned.flows.valuation).toBeNull();
    expect(unsigned.docs.some((d) => d.id === "ens_rd311_2022:op.acc.6")).toBe(true); // official text is public
  });

  it("shows the FAQ as reviewed once the owner has signed it", () => {
    // Signed by the owner in session on 2026-11-23 (#357).
    const cards = index.docs.filter((d) => d.kind === "faq");
    expect(cards.length).toBe(faq.entries.length);
    expect([faq.reviewed_by, faq.reviewed_on]).toEqual(["David Muñoz", "2026-11-23"]);
    for (const card of cards) expect(card.cite[0]).toMatchObject({ kind: "faq", reviewed: true });
    const unsigned = buildIndex(CATALOG, { ...faq, reviewed_by: null });
    expect(unsigned.docs.find((d) => d.kind === "faq")?.cite[0]).toMatchObject({ reviewed: false });
  });

  it("carries the reporting clocks of NIS2 and the GDPR with their official texts", () => {
    const nis2 = index.flows.clocks.find((set) => set.framework === "nis2");
    expect(nis2?.clocks.map((c) => [c.key, c.hours, c.months])).toEqual([["early_warning", 24, null], ["notification", 72, null], ["final_report", null, 1]]);
    expect(nis2?.criteria).toEqual(["art23.3"]);
    expect(index.flows.clocks.find((set) => set.framework === "gdpr_art32")?.clocks[0]).toMatchObject({ hours: 72, code: "art33.1" });
  });

  it("lists the ENS measures that have signed evidence", () => {
    expect(index.flows.measures).toHaveLength(73);
    expect(index.flows.measures[0]).toMatchObject({ code: "org.1" });
  });

  it("stays within the size budget", () => {
    const size = gzippedSize(index);
    expect(size).toBeLessThan(BUDGET_BYTES);
    console.info(`assistant index: ${index.docs.length} documents, ${size} bytes gzipped`);
  });
});
