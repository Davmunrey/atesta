"use client";

import { useTranslations } from "next-intl";
import fixture from "@/content/landing-fixture.json";
import { Icon } from "../icons";
import { CountUp } from "./count-up";
import { ViewFrame } from "./view-frame";

const ICON = { overdue: "overdue", missing: "missing", pending: "pending" } as const;

/**
 * The overview, drawn from the landing fixture (landing-legal spec, L2 and L3): the product's own
 * figures and vocabulary, not a screenshot. ENS codes and names are the catalog's (RD 311/2022,
 * anexo II), checked by a unit test. Motion is CSS only and rests on the final state.
 */
export function OverviewView() {
  const t = useTranslations("landing.view");
  const kpi = useTranslations("console.kpi");
  const c = fixture.counts;
  const segments = [["implemented", c.implemented], ["partial", c.partial], ["missing", c.not_implemented], ["na", c.not_applicable]] as const;
  return <ViewFrame label={t("label")} context={fixture.organization}>
    <div className="lv-body">
      <p className="lv-title"><strong>{fixture.framework}</strong> <span>{t("category", { category: fixture.category })}</span></p>
      <dl className="lv-kpis">
        <div><dt>{kpi("assessed")}</dt><dd><mark className="hl lv-figure"><CountUp value={c.assessed} /></mark> <span>{kpi("ofTotal", { total: c.total })}</span></dd></div>
        <div><dt>{kpi("implemented")}</dt><dd><CountUp value={c.implemented} /> <span>{kpi("ofTotal", { total: c.total })}</span></dd></div>
        <div><dt>{kpi("overdue")}</dt><dd><CountUp value={c.overdue} /></dd><dd className="lv-state" data-severity="overdue"><Icon name="overdue" width={16} height={16} />{kpi("act")}</dd></div>
        <div><dt>{kpi("unowned")}</dt><dd><CountUp value={c.unowned} /></dd><dd className="lv-state" data-severity="overdue"><Icon name="overdue" width={16} height={16} />{kpi("act")}</dd></div>
      </dl>
      <svg className="lv-distribution" viewBox={`0 0 ${c.total} 4`} preserveAspectRatio="none" aria-hidden="true">
        <rect className="lv-track" x="0" y="0" width={c.total} height="4" />
        {segments.map(([key, n], i) => <rect key={key} className={`lv-part-${key}`} x={segments.slice(0, i).reduce((x, [, m]) => x + m, 0)} y="0" width={n} height="4" />)}
      </svg>
      <p className="lv-legend">{t("bar", { implemented: c.implemented, partial: c.partial, missing: c.not_implemented, na: c.not_applicable })}</p>
      <p className="lv-now">{t("now")}</p>
      <ul className="lv-rows">{fixture.attention.map((item) => <li key={item.code}>
        <span className="lv-code">{item.code}</span>
        <span lang="es" className="lv-name">{item.title_es}</span>
        <span className="badge" data-severity={item.state}><Icon name={ICON[item.state as keyof typeof ICON]} />{t(`state.${item.state as keyof typeof ICON}`)}</span>
      </li>)}</ul>
    </div>
  </ViewFrame>;
}
