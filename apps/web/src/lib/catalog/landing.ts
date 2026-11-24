import { readFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";

/**
 * The landing's catalog content (landing-legal amendment A4, issue 393), read at build time so no
 * official text is typed by hand (CLAUDE.md rule 10): one ENS measure for the hero, and one common
 * control with the requirements it answers in each framework, from signed mappings only. Build-time
 * only: it reads the file system, so only server components and tests import it.
 */
type GuideRef = { guide: string; edition: string; section: string; page: number };
export type Evidence = { es: string; en: string; ref: GuideRef };
export type HeroMeasure = { code: string; title: string; section: string; source: string; paragraphs: string[]; level: string; rule: string; evidence: Evidence[] };
export type MappingRow = { framework: string; id: string; reference: string; title_es: string; title_en: string | null; source: string };
export type FrameworkMapping = { control: { id: string; title_es: string; title_en: string }; rows: MappingRow[] };
export type LandingCatalog = { measure: HeroMeasure; mapping: FrameworkMapping };

/** The hero's measure: authentication, from reinforcement R8 (two factors from uncontrolled zones,
 *  such as the Internet) to its clause, which is highlighted. R8 applies at every level. */
const MEASURE = { code: "op.acc.6", from: "Refuerzo R8-", to: "– [op.acc.6.r8.1]", level: "MEDIO" };
/** A control signed for all four frameworks on 2026-11-23. */
const CONTROL = "ctl.app_governance";
const PACKS = ["ens_rd311_2022", "nis2", "gdpr_art32", "dora"] as const;

type Requirement = { id: string; title_es: string; title_en: string | null; source: string; attributes: Record<string, unknown> };
type Mapping = { requirement_id: string; control_id: string; reviewed_by: string | null };

const read = <T>(catalog: string, path: string) => load(readFileSync(join(catalog, path), "utf8")) as T;
const requirements = (catalog: string, pack: string) => read<{ requirements: Requirement[] }>(catalog, `frameworks/${pack}/requirements.yaml`).requirements;

function heroMeasure(catalog: string): HeroMeasure {
  const r = requirements(catalog, "ens_rd311_2022").find((x) => x.id === MEASURE.code);
  if (!r) throw new Error(`${MEASURE.code} is missing from the ENS pack`);
  const text = String(r.attributes.official_text_es).split("\n\n");
  const start = text.findIndex((p) => p.startsWith(MEASURE.from));
  const end = text.findIndex((p) => p.startsWith(MEASURE.to));
  if (start < 0 || end < start) throw new Error(`${MEASURE.code}: the excerpt is no longer in the official text`);
  const rule = (r.attributes.selection_rules as { level: string; rule: string }[]).find((x) => x.level === MEASURE.level)?.rule;
  // Only reviewed guides reach a public page; the reviewer's name stays in the catalog.
  const expected = r.attributes.expected_evidence as { reviewed_by?: string | null; items: Evidence[] } | undefined;
  if (!rule || !expected?.reviewed_by) throw new Error(`${MEASURE.code}: the proposal rule changed or the evidence guide is unreviewed`);
  const evidence = expected.items.map(({ es, en, ref }) => ({ es, en, ref }));
  return { code: r.id, title: r.title_es, section: String(r.attributes.section), source: r.source, paragraphs: text.slice(start, end + 1), level: MEASURE.level, rule, evidence };
}

function mapping(catalog: string): FrameworkMapping {
  const control = read<{ id: string; title_es: string; title_en: string }>(catalog, `controls/${CONTROL.replace("ctl.", "")}.yaml`);
  const rows = PACKS.flatMap((pack): MappingRow[] => {
    const signed = read<{ mappings: Mapping[] }>(catalog, `frameworks/${pack}/mappings.yaml`).mappings.find((m) => m.control_id === CONTROL && m.reviewed_by);
    const r = signed && requirements(catalog, pack).find((x) => x.id === signed.requirement_id);
    if (!r) return [];
    // The ENS cites its measure code; the EU acts cite their article, in the catalog's own words.
    const reference = pack === "ens_rd311_2022" ? r.id : String(r.attributes.section);
    return [{ framework: pack, id: r.id, reference, title_es: r.title_es, title_en: r.title_en, source: r.source }];
  });
  return { control: { id: control.id, title_es: control.title_es, title_en: control.title_en }, rows };
}

export function loadLandingCatalog(catalog = join(process.cwd(), "../../catalog")): LandingCatalog {
  return { measure: heroMeasure(catalog), mapping: mapping(catalog) };
}
