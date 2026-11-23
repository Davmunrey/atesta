"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { BrandMark } from "../brand-mark";

/** Every product view's frame (amendment A1): an ink bar with the mark, the highlighter tab and
 *  the "sample data" label, because the fixture is illustrative (L3). */
export function ViewFrame({ label, context, paper = false, children }: { label: string; context?: ReactNode; paper?: boolean; children: ReactNode }) {
  const t = useTranslations("landing");
  return <figure className={`landing-view${paper ? " lm-paper" : ""}`} aria-label={label}>
    <div className="lv-bar-top">
      <BrandMark className="lv-seal" />
      {context ? <span className="lv-context">{context}</span> : null}
      <span className="lv-sample">{t("sample")}</span>
    </div>
    {children}
  </figure>;
}
