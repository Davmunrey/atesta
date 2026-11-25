"use client";

import { useFormatter, useTranslations } from "next-intl";
import { AssistantLauncher } from "@/components/assistant/launcher";
import { BrandMark } from "@atesta/ui/brand-mark";
import { Icon } from "@atesta/ui/icons";
import { ViewFrame } from "@/components/landing/view-frame";
import fixture from "@/content/landing-fixture.json";
import { legalEntity } from "@/content/legal-entity";

const POINTS = ["p1", "p2", "p3"] as const;

/** The console's portfolio, drawn from sample data with its own column names (A3, issue 381). */
function PortfolioView() {
  const t = useTranslations("portfolio");
  const page = useTranslations("consultoras");
  const format = useFormatter();
  return <ViewFrame label={page("view")} context={t("title")}>
    <div className="lv-body">
      <div className="table-region public-table portfolio-sample" role="region" tabIndex={0} aria-label={t("title")}>
        <table>
          <thead><tr>
            <th scope="col">{t("organization")}</th><th scope="col">{t("assessed")}</th><th scope="col">{t("overdue")}</th>
            <th scope="col">{t("routines")}</th><th scope="col">{t("lastAssessed")}</th>
          </tr></thead>
          <tbody>{fixture.portfolio.map((x) => (
            <tr key={x.name}>
              <th scope="row">{x.name}</th>
              <td data-label={t("assessed")}>{x.started ? t("ofTotal", { assessed: x.assessed, total: x.total }) : t("notStartedCell")}</td>
              <td data-label={t("overdue")}>{x.overdue > 0 ? <span className="badge" data-severity="overdue"><Icon name="overdue" />{format.number(x.overdue)}</span> : format.number(0)}</td>
              <td data-label={t("routines")}>{x.pending === 0 ? t("noRoutines") : x.pendingOverdue > 0 ? t("pendingWithOverdue", { count: x.pending, overdue: x.pendingOverdue }) : t("pending", { count: x.pending })}</td>
              <td data-label={t("lastAssessed")}>{x.last ? format.dateTime(new Date(`${x.last}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) : t("never")}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  </ViewFrame>;
}

/** /consultoras (landing-legal amendment A3, issue 381): many clients, one sign-in. No partner or
 *  customer claims; the portfolio is sample data. */
export default function Consultoras() {
  const t = useTranslations("consultoras");
  const landing = useTranslations("landing");
  const mail = `mailto:${legalEntity.email}`;
  return (
    <main id="content" tabIndex={-1} className="landing consultancies-page">
      <section className="page-hero page-hero-wide" aria-labelledby="consultoras-title">
        <div className="page-hero-copy">
          <h1 id="consultoras-title" className="landing-title">{t.rich("title", { hl: (chunks) => <mark className="hl">{chunks}</mark> })}</h1>
          <p className="landing-sub">{t("sub")}</p>
          <div className="landing-actions"><a href={mail} className="landing-cta">{landing("requestAccess")}</a><a href="/producto" className="landing-signin">{landing("more")}</a></div>
        </div>
        <div className="product-view"><PortfolioView /></div>
      </section>

      <section className="page-band" aria-labelledby="consultoras-how">
        <h2 id="consultoras-how" className="landing-h2">{t("how")}</h2>
        <ul className="landing-steps">{POINTS.map((k) => <li key={k}>
          <h3 className="landing-step-title">{t(`${k}.title`)}</h3>
          <p className="landing-step-body">{t(`${k}.body`)}</p>
        </li>)}</ul>
      </section>

      <section className="landing-close" aria-labelledby="consultoras-close">
        <BrandMark className="landing-close-seal" />
        <h2 id="consultoras-close" className="landing-close-title">{t("close")}</h2>
        <a href={mail} className="landing-cta landing-cta-ink">{landing("requestAccess")}</a>
      </section>
      <AssistantLauncher surface="landing" />
    </main>
  );
}
