/**
 * Build step (assistant spec): writes the assistant's static index from the catalog and the
 * product FAQ. It keeps only content that is public or signed: official texts, blocks with
 * `reviewed_by`, reporting clocks that point at official texts, and the FAQ (marked unreviewed
 * until the owner signs it). Mappings, guides and other candidates stay out; so does any
 * customer data, which the catalog never holds.
 * Usage: node scripts/assistant-index.ts (before next build). Writes public/assistant/index.json.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import { load } from "js-yaml";
import type { Citation, ClockSet, Doc, FlowData, GuideRef, Index, Item, Text } from "../src/lib/assistant/types";

/** v1 corpus (assistant spec). DORA, its RTS and the NIS2 Implementing Regulation come later. */
export const CORPUS = ["ens_rd311_2022", "nis2", "gdpr_art32", "lopdgdd"] as const;
/** Gzipped size budget of the index (assistant spec). */
export const BUDGET_BYTES = 250_000;

type Raw = Record<string, unknown>;
const obj = (value: unknown): Raw => (value && typeof value === "object" && !Array.isArray(value) ? (value as Raw) : {});
const list = (value: unknown): Raw[] => (Array.isArray(value) ? value.map(obj) : []);
const str = (value: unknown): string | null => (typeof value === "string" && value.trim() ? value : null);
const num = (value: unknown): number | null => (typeof value === "number" ? value : null);
const text = (es: unknown, en: unknown): Text => ({ es: str(es), en: str(en) });
const signed = (block: Raw): boolean => str(block.reviewed_by) !== null;

function guideRef(value: unknown): GuideRef | null {
  const ref = obj(value);
  const guide = str(ref.guide), edition = str(ref.edition), page = num(ref.page);
  const section = typeof ref.section === "number" ? String(ref.section) : str(ref.section);
  return guide && edition && section && page !== null ? { guide, edition, section, page } : null;
}
const guideCite = (ref: GuideRef): Citation => ({ kind: "guide", ...ref });

type Pack = { id: string; name: string; attributes: Raw; requirements: Raw[] };

function readPack(catalog: string, id: string): Pack {
  const dir = join(catalog, "frameworks", id);
  const pack = obj(load(readFileSync(join(dir, "pack.yaml"), "utf8")));
  const requirements = list(obj(load(readFileSync(join(dir, "requirements.yaml"), "utf8"))).requirements);
  return { id, name: str(pack.name) ?? id, attributes: obj(pack.attributes), requirements };
}

function groupKeywords(pack: Pack, code: string): string[] {
  return list(pack.attributes.groups_es)
    .filter((group) => { const prefix = str(group.prefix); return prefix !== null && (code === prefix || code.startsWith(`${prefix}.`)); })
    .flatMap((group) => [str(group.title), str(group.title_en)].filter((v): v is string => v !== null));
}

function officialCite(pack: Pack, requirement: Raw): Citation | null {
  const code = str(requirement.id), url = str(requirement.source);
  if (!code || !url?.startsWith("https://")) return null;
  const section = obj(requirement.attributes).section;
  return { kind: "official", framework: pack.id, frameworkName: pack.name, code, section: str(section) ?? (typeof section === "number" ? String(section) : null), url };
}

function requirementDocs(pack: Pack): Doc[] {
  return pack.requirements.flatMap((requirement): Doc[] => {
    const attributes = obj(requirement.attributes);
    const code = str(requirement.id), cite = officialCite(pack, requirement);
    const body = text(attributes.official_text_es, attributes.official_text_en);
    if (!code || !cite || (!body.es && !body.en)) return [];
    const title = text(requirement.title_es, requirement.title_en);
    const keywords = [pack.name, ...groupKeywords(pack, code)];
    const docs: Doc[] = [{ id: `${pack.id}:${code}`, kind: "requirement", framework: pack.id, code, title, text: body, items: [], keywords, cite: [cite] }];
    const evidence = obj(attributes.expected_evidence);
    if (signed(evidence)) {
      const items = list(evidence.items).flatMap((item): Item[] => {
        const ref = guideRef(item.ref);
        const line = text(item.es, item.en);
        return ref && line.es ? [{ text: line, cite: guideCite(ref) }] : [];
      });
      const refs = [...new Map(items.map((item) => [JSON.stringify(item.cite), item.cite])).values()];
      if (items.length > 0) docs.push({ id: `${pack.id}:${code}:evidence`, kind: "evidence", framework: pack.id, code, title, text: { es: null, en: null }, items, keywords: [...keywords, "evidencias", "evidence", "CCN-STIC 808", "auditoría", "audit"], cite: refs });
    }
    return docs;
  });
}

function valuation(pack: Pack): { docs: Doc[]; flow: FlowData["valuation"] } {
  const guide = obj(pack.attributes.scope_guide);
  if (!signed(guide)) return { docs: [], flow: null };
  const categoryByLevel = Object.fromEntries(Object.entries(obj(guide.category_by_level)).flatMap(([level, category]) => (str(category) ? [[level, category as string]] : [])));
  const axis = str(guide.category_axis) ?? "";
  const labels = Object.fromEntries(list(pack.attributes.term_labels).flatMap((label) => (str(label.term) ? [[label.term as string, text(label.es, label.en)]] : [])));
  const steps = list(guide.steps).flatMap((step) => {
    const ref = guideRef(step.ref), key = str(step.key), asset = str(step.asset), question = text(step.es, step.en);
    return ref && key && asset && question.es ? [{ asset, key, question, cite: ref }] : [];
  });
  const notes = list(guide.notes).flatMap((note): Item[] => {
    const ref = guideRef(note.ref), line = text(note.es, note.en);
    return ref && line.es ? [{ text: line, cite: guideCite(ref) }] : [];
  });
  const base = ["CCN-STIC 803", "valoración", "valuation", "nivel", "level", "dimensión"];
  const categoryWords = [axis, "category", ...Object.values(categoryByLevel), ...Object.keys(categoryByLevel)];
  const docs: Doc[] = [
    ...steps.map((step): Doc => ({ id: `${pack.id}:803:${step.key}`, kind: "valuation", framework: pack.id, code: null, title: labels[step.key] ?? { es: step.key, en: step.key }, text: step.question, items: [], keywords: base, cite: [guideCite(step.cite)] })),
    ...notes.map((note, n): Doc => ({ id: `${pack.id}:803:note${n + 1}`, kind: "valuation", framework: pack.id, code: null, title: { es: null, en: null }, text: note.text, items: [], keywords: axis && note.text.es?.includes(axis) ? [...base, ...categoryWords] : base, cite: [note.cite] })),
  ];
  return { docs, flow: { framework: pack.id, steps, notes, categoryByLevel, labels } };
}

function profiles(pack: Pack): { docs: Doc[]; flow: FlowData["profiles"] } {
  const found = list(pack.attributes.scope_profiles).filter(signed).flatMap((profile) => {
    const key = str(profile.key), refs = list(profile.refs).map(guideRef).filter((r): r is GuideRef => r !== null);
    if (!key || refs.length === 0) return [];
    const levels = Object.fromEntries(Object.entries(obj(profile.levels)).flatMap(([code, level]) => (str(level) ? [[code, level as string]] : [])));
    const criteria = Object.fromEntries(Object.entries(obj(profile.criteria)).flatMap(([code, value]) => {
      const ref = obj(value), page = num(ref.page), section = str(ref.section);
      return page !== null && section ? [[code, { section, page }]] : [];
    }));
    return [{ key, title: text(profile.title_es, profile.title_en), summary: text(profile.summary_es, profile.summary_en), refs, levels, criteria }];
  });
  if (found.length === 0) return { docs: [], flow: null };
  const docs = found.map((profile): Doc => ({ id: `${pack.id}:890C:${profile.key}`, kind: "profile", framework: pack.id, code: null, title: profile.title, text: profile.summary, items: [], keywords: ["CCN-STIC 890C", "perfil", "profile", "esencial", "essential", "PCE", "requisitos fundamentales"], cite: profile.refs.map(guideCite) }));
  return { docs, flow: { framework: pack.id, profiles: found } };
}

function clocks(pack: Pack): { docs: Doc[]; flow: ClockSet[] } {
  const byCode = new Map(pack.requirements.map((requirement) => [str(requirement.id), requirement]));
  const sets = new Map<string, ClockSet>();
  const docs: Doc[] = [];
  for (const clock of list(pack.attributes.reporting_clocks)) {
    const key = str(clock.key), code = str(clock.requirement), needs = str(clock.needs);
    const requirement = code ? byCode.get(code) : undefined;
    const cite = requirement ? officialCite(pack, requirement) : null;
    if (!key || !code || !needs || !requirement || !cite) continue;
    const attributes = obj(requirement.attributes);
    const entry = { key, title: text(clock.title_es, clock.title_en), hours: num(clock.hours), months: num(clock.months), after: str(clock.after), code };
    const set = sets.get(needs) ?? { framework: pack.id, frameworkName: pack.name, needs, clocks: [], criteria: [] };
    set.clocks.push(entry);
    sets.set(needs, set);
    const duration = entry.hours !== null ? [`${entry.hours}`, "horas", "hours"] : entry.months !== null ? [`${entry.months}`, "mes", "month"] : [];
    docs.push({ id: `${pack.id}:clock:${key}`, kind: "clock", framework: pack.id, code, title: entry.title, text: text(attributes.official_text_es, attributes.official_text_en), items: [], keywords: [pack.name, "plazo", "deadline", "notificación", "incidente", "incident", ...duration], cite: [cite] });
  }
  for (const criterion of list(pack.attributes.incident_criteria)) {
    const set = sets.get(str(criterion.needs) ?? ""), code = str(criterion.requirement);
    if (set && code && byCode.has(code)) set.criteria.push(code);
  }
  return { docs, flow: [...sets.values()] };
}

type Faq = { reviewed_by: string | null; entries: { id: string; question: Text; answer: Text; keywords?: string[] }[] };

function faqDocs(faq: Faq): Doc[] {
  const reviewed = Boolean(faq.reviewed_by);
  return faq.entries.map((entry) => ({ id: `faq:${entry.id}`, kind: "faq", framework: null, code: null, title: entry.question, text: entry.answer, items: [], keywords: ["Atesta", ...(entry.keywords ?? [])], cite: [{ kind: "faq", id: entry.id, reviewed }] }));
}

/** Builds the index from a catalog folder and the FAQ. Pure apart from reading files. */
export function buildIndex(catalog: string, faq: Faq): Index {
  const packs = CORPUS.map((id) => readPack(catalog, id));
  const docs: Doc[] = [];
  const flows: FlowData = { valuation: null, profiles: null, clocks: [], measures: [] };
  for (const pack of packs) {
    docs.push(...requirementDocs(pack));
    const v = valuation(pack), p = profiles(pack), c = clocks(pack);
    docs.push(...v.docs, ...p.docs, ...c.docs);
    flows.valuation ??= v.flow;
    flows.profiles ??= p.flow;
    flows.clocks.push(...c.flow);
  }
  docs.push(...faqDocs(faq));
  const evidence = new Set(docs.filter((doc) => doc.kind === "evidence").map((doc) => doc.code));
  flows.measures = docs.filter((doc) => doc.kind === "requirement" && evidence.has(doc.code)).map((doc) => ({ code: doc.code as string, title: doc.title }));
  const uncited = docs.filter((doc) => doc.cite.length === 0).map((doc) => doc.id);
  if (uncited.length > 0) throw new Error(`assistant index: documents without a citation: ${uncited.join(", ")}`);
  return { version: 1, docs, flows };
}

export const gzippedSize = (index: Index): number => gzipSync(JSON.stringify(index)).length;

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const web = fileURLToPath(new URL("..", import.meta.url));
  const faq = JSON.parse(readFileSync(join(web, "src/content/assistant-faq.json"), "utf8")) as Faq;
  const index = buildIndex(join(web, "../../catalog"), faq);
  const size = gzippedSize(index);
  if (size > BUDGET_BYTES) throw new Error(`assistant index is ${size} bytes gzipped; the budget is ${BUDGET_BYTES}`);
  const out = join(web, "public/assistant/index.json");
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify(index));
  console.log(`assistant index: ${index.docs.length} documents, ${size}/${BUDGET_BYTES} bytes gzipped`);
}
