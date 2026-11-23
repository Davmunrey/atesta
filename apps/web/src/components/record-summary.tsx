"use client";

import { useTranslations } from "next-intl";
import { Icon } from "./icons";

/** One figure; `attention` adds its state as icon plus text (needs action / up to date). */
export type Figure = { label: string; value: string; attention?: boolean };

/** Executive summary at the top of a records page (ui-polish spec): a sentence, then key figures
 *  in the overview's KPI style. State is written, never colour alone. */
export function RecordSummary({ lead, figures }: { lead: string; figures: Figure[] }) {
  const s = useTranslations("summary");
  const c = useTranslations("console.kpi");
  return <section className="record-summary" aria-label={s("label")}>
    <p className="record-summary-lead">{lead}</p>
    <dl className="kpis kpis-fit">{figures.map((f) => <div className="kpi" key={f.label}>
      <dt>{f.label}</dt><dd>{f.value}</dd>
      {f.attention === undefined ? null : <dd className="kpi-state" data-severity={f.attention ? "overdue" : "done"}>
        <Icon name={f.attention ? "overdue" : "done"} width={16} height={16} />{c(f.attention ? "act" : "clear")}</dd>}
    </div>)}</dl>
  </section>;
}
