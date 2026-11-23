/**
 * Search normalisation (assistant spec): case and accents folded, ENS measure codes kept as one
 * token whatever their spelling, a light ES and EN stemmer, stop words dropped, and curated
 * synonym phrases. Pure; shared by the index tests and the browser.
 */

const GROUPS = "info|cont|nub|acc|exp|ext|mon|per|com|pl|if|eq|si|sw|s";
/** op.acc.6, OP ACC 6, op-acc-6, opacc6; org.1, org 1. Reinforcement suffixes are left aside. */
const CODE = new RegExp(`\\b(?:(org)[\\s._-]*(\\d{1,2})|(op|mp)[\\s._-]*(${GROUPS})[\\s._-]*(\\d{1,2}))(?![\\d])`, "g");

const STOP = new Set([
  "a", "al", "ante", "como", "con", "cual", "cuales", "de", "del", "el", "en", "es", "esta", "este", "hay", "la", "las", "lo", "los",
  "me", "mi", "mis", "o", "para", "por", "que", "se", "si", "son", "su", "sus", "tengo", "un", "una", "uno", "y", "yo",
  "about", "an", "and", "are", "do", "does", "for", "how", "i", "in", "is", "it", "my", "of", "on", "or", "the", "to", "what", "which", "with",
]);

/** Lower case with accents folded; ñ becomes n, which is how people type without a Spanish keyboard. */
export const fold = (value: string): string => value.normalize("NFD").replace(/\p{M}+/gu, "").toLowerCase();

/** Light stemmer: plural endings, then a final a/e/o, so incidente and incidentes meet. */
export function stem(word: string): string {
  if (/^\d+$/.test(word) || word.length <= 3) return word;
  let w = word;
  if (w.length > 4 && w.endsWith("ies")) w = `${w.slice(0, -3)}y`;
  else if (w.length > 4 && w.endsWith("es")) w = w.slice(0, -2);
  else if (w.endsWith("s") && !w.endsWith("ss")) w = w.slice(0, -1);
  if (w.length > 4 && /[aeo]$/.test(w)) w = w.slice(0, -1);
  return w;
}

/** Tokens of a text: codes first (as `op.acc.6`), then stemmed words without stop words. */
export function tokens(value: string): string[] {
  const folded = fold(value);
  const codes: string[] = [];
  const rest = folded.replace(CODE, (_m, org: string | undefined, orgN: string | undefined, frame: string | undefined, group: string | undefined, n: string | undefined) => {
    codes.push(org ? `org.${Number(orgN)}` : `${frame}.${group}.${Number(n)}`);
    return " ";
  });
  const words = rest.split(/[^\p{L}\p{N}]+/u).filter((w) => w.length > 0 && !STOP.has(w)).map(stem);
  return [...codes, ...words];
}

/** A normalised code (`op.acc.6`) for an ENS-style requirement id, or the folded id otherwise. */
export const codeToken = (code: string): string => tokens(code)[0] ?? fold(code);

export type Synonyms = { groups: string[][] };
/** Each phrase as a token list, grouped; phrases that normalise to nothing are dropped. */
export type SynonymTable = string[][][];

export const synonymTable = (synonyms: Synonyms): SynonymTable =>
  synonyms.groups.map((group) => group.map(tokens).filter((phrase) => phrase.length > 0)).filter((group) => group.length > 1);

/** A query term: alternatives the document may match, each a phrase whose tokens must all appear. */
export type Term = { alternatives: string[][] };

const startsWith = (list: string[], at: number, phrase: string[]): boolean => phrase.every((token, i) => list[at + i] === token);

/** Splits a query into terms, joining a synonym phrase into one term with every phrase of its group. */
export function queryTerms(query: string, table: SynonymTable): Term[] {
  const list = tokens(query);
  const terms: Term[] = [];
  for (let at = 0; at < list.length;) {
    let best: { group: string[][]; length: number } | null = null;
    for (const group of table) {
      for (const phrase of group) {
        if (phrase.length > (best?.length ?? 0) && startsWith(list, at, phrase)) best = { group, length: phrase.length };
      }
    }
    if (best) {
      terms.push({ alternatives: best.group });
      at += best.length;
    } else {
      terms.push({ alternatives: [[list[at] as string]] });
      at += 1;
    }
  }
  return terms;
}
