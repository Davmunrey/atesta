"use client";

import { useTranslations } from "next-intl";
import { createContext, type ReactNode, useContext } from "react";
import { BrandMark } from "../brand-mark";

/** A section that states "Datos de ejemplo" once for all its frames (A4) provides `true`. */
export const SampleLabelled = createContext(false);

/** Every product view's frame (amendment A1): an ink bar with the mark, the highlighter tab and
 *  the "sample data" label, because the fixture is illustrative (L3), unless its section says it. */
export function ViewFrame({ label, context, paper = false, children }: { label: string; context?: ReactNode; paper?: boolean; children: ReactNode }) {
  const t = useTranslations("landing");
  const labelled = useContext(SampleLabelled);
  return <figure className={`landing-view${paper ? " lm-paper" : ""}`} aria-label={label}>
    <div className="lv-bar-top">
      <BrandMark className="lv-seal" />
      {context ? <span className="lv-context">{context}</span> : null}
      {labelled ? null : <span className="lv-sample">{t("sample")}</span>}
    </div>
    {children}
  </figure>;
}
