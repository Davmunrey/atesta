/** The assistant's index (assistant spec): catalog content quoted verbatim, each piece cited. */

/** One text in both languages; `en` is null when no English is published. */
export type Text = { es: string | null; en: string | null };

export type GuideRef = { guide: string; edition: string; section: string; page: number };

export type Citation =
  | { kind: "official"; framework: string; frameworkName: string; code: string; section: string | null; url: string }
  | ({ kind: "guide" } & GuideRef)
  | { kind: "faq"; id: string; reviewed: boolean };

export type DocKind = "requirement" | "evidence" | "profile" | "valuation" | "clock" | "faq";

/** A cited item inside a card: one expected-evidence line, one profile value. */
export type Item = { text: Text; cite: Citation };

export type Doc = {
  id: string;
  kind: DocKind;
  /** Pack id, null for the FAQ. */
  framework: string | null;
  /** Requirement code, when the card is about one requirement. */
  code: string | null;
  title: Text;
  /** Verbatim body text. */
  text: Text;
  items: Item[];
  /** Search-only terms (group names, labels); never shown. */
  keywords: string[];
  cite: Citation[];
};

export type ValuationStep = { asset: string; key: string; question: Text; cite: GuideRef };
export type Profile = {
  key: string;
  title: Text;
  summary: Text;
  refs: GuideRef[];
  levels: Record<string, string>;
  criteria: Record<string, { section: string; page: number }>;
};
export type Clock = {
  key: string;
  title: Text;
  hours: number | null;
  months: number | null;
  after: string | null;
  code: string;
};
export type ClockSet = { framework: string; frameworkName: string; needs: string; clocks: Clock[]; criteria: string[] };

/** Structured catalog data the guided flows walk; every value comes from a signed block. */
export type FlowData = {
  valuation: { framework: string; steps: ValuationStep[]; notes: Item[]; categoryByLevel: Record<string, string>; labels: Record<string, Text> } | null;
  profiles: { framework: string; profiles: Profile[] } | null;
  clocks: ClockSet[];
  measures: { code: string; title: Text }[];
};

export type Index = { version: 1; docs: Doc[]; flows: FlowData };
