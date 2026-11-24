"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import type { components } from "@/lib/api/schema";
import type { Readiness } from "@/lib/api/register-hooks";
import { percent } from "@atesta/ui/format";
import { orgFramework, orgFrameworks } from "@/lib/org";
import { Panel } from "@atesta/ui/page-frame";

type Framework = components["schemas"]["FrameworkSummary"];

/**
 * One line per framework on the home (console-unification spec): its name as a link and where it
 * stands. The lead framework's measures assessed is the page's one key figure (DESIGN.md).
 */
export function FrameworkLines({ frameworks, readiness, orgId }: { frameworks: Framework[]; readiness: Readiness[]; orgId: string }) {
  const t = useTranslations("cockpit");
  const d = useTranslations("dashboard");
  const locale = useLocale();
  const progress = new Map(readiness.map((r) => [r.key, r]));
  const assessed = (f: Framework) => progress.get(f.key)?.assessed ?? 0;
  const share = (f: Framework) => assessed(f) / Math.max(f.requirements, 1);
  const rank = (f: Framework) => (f.snapshot || assessed(f) > 0 ? 0 : 1);
  const lines = frameworks.filter((f) => f.requirements > 0).map((f, i) => [f, i] as const)
    .sort(([a, i], [b, j]) => rank(a) - rank(b) || share(b) - share(a) || i - j).map(([f]) => f);
  const lead = lines.find((f) => assessed(f) > 0)?.key;
  return <Panel title={t("frameworks")} actions={frameworks.length > 0
    ? <Link href={orgFrameworks(orgId)} className="text-link underline text-sm action-link">{t("allFrameworks")}</Link> : null}>
    {frameworks.length === 0 ? <div className="dashboard-empty"><h3>{d("emptyFrameworks")}</h3><p>{d("emptyFrameworksHelp")}</p></div>
      : <ul className="framework-lines">{lines.map((f) => {
        const r = progress.get(f.key);
        const state = r && r.assessed > 0
          ? t.rich("line", { assessed: r.assessed, total: r.total, implemented: r.implemented,
            key: (c) => f.key === lead ? <span className="key-figure">{c}</span> : c })
          : f.snapshot ? (f.snapshot.score === null ? t("lineUnscored") : t("lineScore", { score: percent(locale, f.snapshot.score) }))
          : t("lineNotStarted");
        return <li key={f.key}><Link href={orgFramework(orgId, f.key)} className="text-link underline">{f.name}</Link>
          <span className="framework-line-state">{state}</span></li>;
      })}</ul>}
  </Panel>;
}
