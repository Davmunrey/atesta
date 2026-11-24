/** Guided-flow logic and helpers (assistant spec). Pure; nothing here judges compliance (ADR-005). */
import { orgFramework } from "@/lib/org";
import type { Locale } from "@atesta/ui/i18n/locale";
import type { Doc, FlowData, Index, Text } from "./types";

export const INDEX_URL = "/assistant/index.json";

/** Fetches the static index; `no-cache` revalidates, so a new release is picked up. */
export async function loadIndex(): Promise<Index> {
  const response = await fetch(INDEX_URL, { cache: "no-cache" });
  if (!response.ok) throw new Error(`assistant index: HTTP ${response.status}`);
  return (await response.json()) as Index;
}

/**
 * The category the catalog's CCN-STIC 803 table gives for the highest level picked, or null until
 * every step has an answer. Levels rank in the table's own order (BAJO, MEDIO, ALTO).
 */
export function categoryFor(flow: NonNullable<FlowData["valuation"]>, picked: Record<string, string>): string | null {
  const order = Object.keys(flow.categoryByLevel);
  const ranks = flow.steps.map((step) => order.indexOf(picked[step.key] ?? ""));
  if (ranks.some((rank) => rank < 0)) return null;
  return flow.categoryByLevel[order[Math.max(...ranks)] as string] ?? null;
}

/** The text to show and its language: Spanish-only text stays Spanish, marked so, never translated. */
export function pick(text: Text, locale: Locale): { value: string; lang: "es" | undefined } | null {
  if (locale === "en" && text.en) return { value: text.en, lang: undefined };
  if (text.es) return { value: text.es, lang: locale === "en" ? "es" : undefined };
  return text.en ? { value: text.en, lang: undefined } : null;
}

const LINKED = new Set<Doc["kind"]>(["requirement", "evidence", "clock"]);

/** The requirement in the organization's framework page, for cards about one requirement. */
export function orgLink(doc: Doc, orgId: string | null | undefined): string | null {
  if (!orgId || !doc.framework || !doc.code || !LINKED.has(doc.kind)) return null;
  return `${orgFramework(orgId, doc.framework)}#req-${doc.code}`;
}
