"use client";

import { useTranslations } from "next-intl";

const FACTS = ["boe", "team", "spain", "readonly", "noai"] as const;

/** Honest proof (A3, owner 23/11/2026): five facts true at publish time, no person's name. */
export function ProofStrip({ onInk = false }: { onInk?: boolean }) {
  const t = useTranslations("public.proof");
  return <ul className={`proof-strip${onInk ? " proof-strip-ink" : ""}`} aria-label={t("label")}>
    {FACTS.map((key) => <li key={key}><strong>{t(`${key}.lead`)}</strong> <span>{t(`${key}.line`)}</span></li>)}
  </ul>;
}
