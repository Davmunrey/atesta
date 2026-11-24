import { readFileSync } from "node:fs";
import { join } from "node:path";
import { load } from "js-yaml";

/**
 * The ENS measures for the public /ens page (landing-legal A3, issue 377), read from the catalog
 * pack at build time so no official text is typed by hand (CLAUDE.md rule 10). Build-time only:
 * it reads the file system, so only server components and tests import it.
 */
export type EnsMeasure = { code: string; title: string; source: string; dimensions: string; rules: [string, string, string] };
export type EnsGroup = { prefix: string; title: string; measures: EnsMeasure[] };
export type EnsFramework = { prefix: string; title: string; groups: EnsGroup[] };
export type EnsCatalog = { source: string; columns: [string, string, string]; frameworks: EnsFramework[] };

const PACK = "frameworks/ens_rd311_2022";
/** Each column pairs a category with the level that leads to it, as the pack's category_by_level says. */
const COLUMNS = [["BÁSICA", "BAJO"], ["MEDIA", "MEDIO"], ["ALTA", "ALTO"]] as const;

type Rule = { level: string; rule: string };
type Requirement = { id: string; title_es: string; source: string; attributes: { selection_basis?: string; selection_rules?: Rule[] } };
type Pack = { source: string; attributes: { groups_es: { prefix: string; title: string }[] } };

export function loadEnsCatalog(catalog = join(process.cwd(), "../../catalog")): EnsCatalog {
  const pack = load(readFileSync(join(catalog, PACK, "pack.yaml"), "utf8")) as Pack;
  const { requirements } = load(readFileSync(join(catalog, PACK, "requirements.yaml"), "utf8")) as { requirements: Requirement[] };
  const groups = pack.attributes.groups_es;
  const measure = (r: Requirement): EnsMeasure => {
    const rules = r.attributes.selection_rules ?? [];
    const cell = ([category, level]: readonly [string, string]) => rules.find((x) => x.level === category || x.level === level)?.rule ?? "";
    return { code: r.id, title: r.title_es, source: r.source, dimensions: (r.attributes.selection_basis ?? "").split(" · ").pop() ?? "", rules: [cell(COLUMNS[0]), cell(COLUMNS[1]), cell(COLUMNS[2])] };
  };
  const within = (prefix: string) => (r: Requirement) => r.id.startsWith(`${prefix}.`);
  const frameworks = groups.filter((g) => !g.prefix.includes(".")).map((top): EnsFramework => {
    const subs = groups.filter((g) => g.prefix.startsWith(`${top.prefix}.`));
    const parts = subs.length ? subs : [top];
    return { prefix: top.prefix, title: top.title, groups: parts.map((g) => ({ prefix: g.prefix, title: g.title, measures: requirements.filter(within(g.prefix)).map(measure) })) };
  });
  return { source: pack.source, columns: COLUMNS.map(([c, l]) => `${c} · ${l}`) as EnsCatalog["columns"], frameworks };
}
