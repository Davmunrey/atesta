"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
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

/** The incident stage (A3, issue 373): its deadline with a bar that fills once (no ticking
 *  clock, so nothing keeps moving) and a timestamped log that settles in. */
export function IncidentView() {
  const t = useTranslations("landing.view.incident");
  return <ViewFrame label={t("label")}>
    <div className="lv-body li-incident">
      <p><strong>{t("title")}</strong><span className="lv-legend li-meta">{t("meta")}</span></p>
      <div className="li-clock">
        <span className="lv-legend">{t("deadline")}</span>
        <span className="badge" data-severity="pending"><Icon name="pending" />{t("state")}</span>
        <span className="li-due">{t("due")}</span>
        <span className="li-bar" aria-hidden="true"><span /></span>
      </div>
      <ol className="li-log">
        <li><span className="lv-code">09:40</span><span>{t("log1")}</span></li>
        <li><span className="lv-code">09:42</span><span>{t("log2")}</span></li>
        <li><span className="lv-code">10:05</span><span>{t("log3")}</span></li>
      </ol>
      <p className="li-source">{t("source")}</p>
    </div>
  </ViewFrame>;
}

/** The assistant (A3, issue 377): a question and its answer, quoted from the ENS pack's reviewed
 *  expected evidence with the guide it comes from; a test keeps the fixture equal to the catalog. */
export function AssistantView() {
  const t = useTranslations("landing.view.assistant");
  const locale = useLocale();
  const a = fixture.assistant;
  return <ViewFrame label={t("label")}>
    <div className="lv-body la-chat">
      <p className="la-question">{t("question", { code: a.code })}</p>
      <div className="la-answer">
        <p className="lv-title"><span className="lv-code">{a.code}</span> <strong lang="es">{a.title_es}</strong></p>
        <ul className="la-items">{a.items.map((item) => <li key={item.es}>{locale === "es" ? item.es : item.en}</li>)}</ul>
        <p className="li-source">{t("cite")} {a.cite}</p>
      </div>
    </div>
  </ViewFrame>;
}

/** Real MCP tools only (a test checks each name against the server's list). */
const API_TOOLS = ["list_gaps", "list_due_items", "get_measure"] as const;

/** API and MCP (A3, issue 377): one real request and the read tools an agent calls. */
export function ApiView() {
  const t = useTranslations("landing.view.api");
  const tools = useTranslations("mcpGuide.tools.list");
  return <ViewFrame label={t("label")}>
    <div className="lv-body la-api">
      <pre className="la-code"><code>{"GET /api/v1/gaps\nAuthorization: Bearer atesta_…"}</code></pre>
      <p className="lm-label">{t("tools")}</p>
      <ul className="la-tools">{API_TOOLS.map((name) => <li key={name} data-tool={name}><span className="lv-code">{name}</span><span>{tools(name)}</span></li>)}</ul>
    </div>
  </ViewFrame>;
}
