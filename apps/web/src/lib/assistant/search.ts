/**
 * The assistant's scorer (assistant spec): BM25 over weighted fields, an exact measure code first,
 * and a threshold under which there is no answer. No search library; built once per page.
 */
import { type SynonymTable, type Term, codeToken, queryTerms, tokens } from "./normalize";
import type { Doc } from "./types";

const FIELDS = { code: 4, title: 3, keywords: 2, text: 1 } as const;
type Field = keyof typeof FIELDS;
const K1 = 1.2;
const B = 0.75;
/** A code match outranks any text match. */
const CODE_BONUS = 100;
/** No answer below this score, or when fewer than this share of the query's terms match. */
export const MIN_SCORE = 2;
export const MIN_COVERAGE = 0.6;
/** Cards scoring under this share of the best one are noise. */
const RELATIVE_FLOOR = 0.35;
export const MAX_RESULTS = 5;

type Entry = { doc: Doc; counts: Record<Field, Map<string, number>>; lengths: Record<Field, number>; code: string | null };
export type Engine = { entries: Entry[]; df: Map<string, number>; average: Record<Field, number>; synonyms: SynonymTable };
export type Hit = { doc: Doc; score: number };

const both = (text: { es: string | null; en: string | null }): string => [text.es, text.en].filter(Boolean).join(" ");

function count(list: string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const token of list) counts.set(token, (counts.get(token) ?? 0) + 1);
  return counts;
}

export function createEngine(docs: Doc[], synonyms: SynonymTable): Engine {
  const entries = docs.map((doc): Entry => {
    const fields: Record<Field, string[]> = {
      code: doc.code ? [codeToken(doc.code)] : [],
      title: tokens(both(doc.title)),
      keywords: tokens(doc.keywords.join(" ")),
      text: tokens([both(doc.text), ...doc.items.map((item) => both(item.text))].join(" ")),
    };
    const counts = Object.fromEntries(Object.entries(fields).map(([field, list]) => [field, count(list)])) as Record<Field, Map<string, number>>;
    const lengths = Object.fromEntries(Object.entries(fields).map(([field, list]) => [field, list.length])) as Record<Field, number>;
    return { doc, counts, lengths, code: doc.code ? codeToken(doc.code) : null };
  });
  const df = new Map<string, number>();
  for (const entry of entries) {
    const seen = new Set(Object.values(entry.counts).flatMap((counts) => [...counts.keys()]));
    for (const token of seen) df.set(token, (df.get(token) ?? 0) + 1);
  }
  const average = Object.fromEntries((Object.keys(FIELDS) as Field[]).map((field) => [field, Math.max(1, entries.reduce((sum, e) => sum + e.lengths[field], 0) / Math.max(1, entries.length))])) as Record<Field, number>;
  return { entries, df, average, synonyms };
}

function tokenScore(engine: Engine, entry: Entry, token: string): number {
  let weighted = 0;
  for (const field of Object.keys(FIELDS) as Field[]) {
    const tf = entry.counts[field].get(token) ?? 0;
    if (tf > 0) weighted += (FIELDS[field] * tf) / (1 - B + (B * entry.lengths[field]) / engine.average[field]);
  }
  if (weighted === 0) return 0;
  const n = engine.entries.length, df = engine.df.get(token) ?? 0;
  const idf = Math.log(1 + (n - df + 0.5) / (df + 0.5));
  return (idf * weighted * (K1 + 1)) / (weighted + K1);
}

/** A term scores its best alternative; a phrase counts only when every token of it is present. */
function termScore(engine: Engine, entry: Entry, term: Term): number {
  let best = 0;
  for (const phrase of term.alternatives) {
    const scores = phrase.map((token) => tokenScore(engine, entry, token));
    if (scores.every((s) => s > 0)) best = Math.max(best, scores.reduce((a, b) => a + b, 0));
  }
  return best;
}

/** The ranked cards for a query, or an empty list when nothing clears the threshold. */
export function search(engine: Engine, query: string): Hit[] {
  const terms = queryTerms(query, engine.synonyms);
  if (terms.length === 0) return [];
  const codes = new Set(tokens(query).filter((token) => token.includes(".")));
  const hits: Hit[] = [];
  for (const entry of engine.entries) {
    let score = 0, matched = 0;
    for (const term of terms) {
      const s = termScore(engine, entry, term);
      if (s > 0) { matched += 1; score += s; }
    }
    if (entry.code && codes.has(entry.code)) score += CODE_BONUS;
    else if (matched / terms.length < MIN_COVERAGE) continue;
    if (score >= MIN_SCORE) hits.push({ doc: entry.doc, score });
  }
  hits.sort((a, b) => b.score - a.score || a.doc.id.localeCompare(b.doc.id));
  const top = hits[0]?.score ?? 0;
  return hits.filter((hit) => hit.score >= top * RELATIVE_FLOOR).slice(0, MAX_RESULTS);
}
