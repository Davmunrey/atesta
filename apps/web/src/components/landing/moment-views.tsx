"use client";

import { useFormatter, useTranslations } from "next-intl";
import fixture from "@/content/landing-fixture.json";
import { Icon } from "../icons";
import { ViewFrame } from "./view-frame";

/** Product moments (landing-legal spec, L7): views of what the console ships, from the fixture. */
export function MeasureView() {
  const t = useTranslations("landing.view.measure");
  const m = fixture.measure;
  return <ViewFrame label={t("label")}>
    <div className="lv-body">
      <p className="lv-title"><span className="lv-code">{m.code}</span> <strong lang="es">{m.title_es}</strong></p>
      <div className="lm-official"><p className="lm-label">{t("official")}</p><p lang="es">{m.excerpt_es}</p></div>
      <div className="lm-assessment"><p className="lm-label">{t("assessment")}</p>
        <p>{t("decision", { level: m.level })} · <span className="badge" data-severity="partial"><Icon name="partial" />{t("implementation")}</span></p>
        <p className="lv-legend">{t("owner")}</p></div>
    </div>
  </ViewFrame>;
}

const RECORDS = [["policies", true], ["access", false], ["training", false], ["incidents", false]] as const;

export function RecordsView() {
  const t = useTranslations("landing.view.records");
  return <ViewFrame label={t("label")}>
    <ul className="lv-body lm-records">{RECORDS.map(([key, act]) => <li key={key}>
      <strong>{t(key)}</strong>
      <span className="badge" data-severity={act ? "overdue" : "done"}><Icon name={act ? "overdue" : "done"} />{t(act ? "act" : "clear")}</span>
      <span className="lm-line">{t(`${key}Line`)}</span>
    </li>)}</ul>
  </ViewFrame>;
}

export function DossierView() {
  const t = useTranslations("landing.view.dossier");
  const format = useFormatter();
  return <ViewFrame label={t("label")} paper>
    <div className="lv-body">
      <p className="lm-label">{t("kicker")}</p>
      <p className="lm-dossier-title">{fixture.framework}</p>
      <p className="lv-legend">{fixture.organization} · <span className="lv-code">{fixture.dossier.catalog}</span> · {format.dateTime(new Date(`${fixture.dossier.generated}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" })}</p>
      <p className="lm-statement">{t("statement")}</p>
      <dl className="lm-sign">{(["name", "role", "date", "signature"] as const).map((k) => <div key={k}><dt>{t(k)}</dt><dd /></div>)}</dl>
    </div>
  </ViewFrame>;
}
