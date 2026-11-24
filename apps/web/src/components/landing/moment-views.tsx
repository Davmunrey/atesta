"use client";

import { useFormatter, useLocale, useTranslations } from "next-intl";
import fixture from "@/content/landing-fixture.json";
import type { HeroMeasure } from "@/lib/catalog/landing";
import { Icon } from "../icons";
import { ExpectedEvidence } from "../expected-evidence";
import { AssessmentFields, AssessmentIntro, AssessmentState, MeasureSheet, OfficialText } from "../measure-sheet";
import { ViewFrame } from "./view-frame";

/** Product moments (landing-legal spec, L7): views of what the console ships. */

/** One ENS measure as the console shows it (A4): the shared measure sheet, sample mode, in a product
 *  frame. The measure, its proposal and official text come from the catalog; the assessment is sample
 *  data. The excerpt's last paragraph is highlighted. */
export function MeasureView({ measure }: { measure: HeroMeasure }) {
  const t = useTranslations("landing.view.hero");
  const assessment = { applicability: "applies", implementation: "partially_implemented", notes: t("note") } as const;
  return <ViewFrame label={t("label")} context={fixture.organization}>
    <div className="lv-body"><MeasureSheet code={measure.code} title={measure.title} titleLang="es" source={measure.source}
      state={<AssessmentState state={assessment.implementation} />}
      record={<>
        <div className="assessment-card"><AssessmentIntro heading={false} proposal={{ decision: "applies", rule: measure.rule, level: measure.level }} />
          <AssessmentFields value={assessment} owner={t("ownerValue")} /></div>
        <ExpectedEvidence variant="sample" evidence={{ items: measure.evidence, reviewed_by: null }} />
      </>}
      law={<><p className="measure-sheet-section">{t("excerpt")}</p><OfficialText text={measure.paragraphs} lang="es" highlightLast /></>} /></div>
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

/** The incident stage (A4): an ENS incident record and its notes. RD 311/2022, art. 33.7 asks a
 *  provider of public entities to notify INCIBE-CERT and sets no deadline in hours, so the view
 *  shows no clock; NIS2 and GDPR clocks are the console's, from their packs. */
const LOG = [["09:40", "log1"], ["09:55", "log2"], ["10:05", "log3"], ["11:20", "log4"]] as const;

export function IncidentView() {
  const t = useTranslations("landing.view.incident");
  return <ViewFrame label={t("label")}>
    <div className="lv-body li-incident">
      <p><strong>{t("title")}</strong><span className="lv-legend li-meta">{t("meta")}</span></p>
      <ol className="li-log">{LOG.map(([time, key]) => <li key={key}><span className="lv-code">{time}</span><span>{t(key)}</span></li>)}</ol>
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
