"use client";

import { useTranslations } from "next-intl";
import { Icon } from "../icons";

const MONTHS = ["m0", "m1", "m2", "m3", "m4", "m5"] as const;

/** "Un año de ENS" (amendment A2): a year of sample data that reveals as it scrolls (CSS view()
 *  timelines inside @supports; without them the list is complete and static). */
export function YearOfEns() {
  const t = useTranslations("landing");
  return <section className="landing-band landing-year" aria-labelledby="year-title">
    <h2 id="year-title" className="landing-h2">{t("year.title")}</h2>
    <div className="landing-year-body">
      <span className="landing-soon landing-sample">{t("sample")}</span>
      <span className="landing-year-line" aria-hidden="true" />
      <ol className="landing-year-list" aria-label={t("view.year.label")}>
        {MONTHS.map((m) => <li key={m}>
          <span className="landing-year-month">{t(`view.year.${m}.month`)}</span>
          <span className="landing-year-text">{m === "m3" ? <Icon name="pending" /> : null}{t(`view.year.${m}.text`)}</span>
        </li>)}
      </ol>
    </div>
  </section>;
}
