"use client";

import { useTranslations } from "next-intl";

const RINGS = ["ENS", "NIS2", "RGPD", "LOPDGDD", "DORA"] as const;

/** "Una evidencia, muchos marcos" (A3, issue 373): common controls at the centre, each framework a
 *  ring around them, the ENS innermost on the highlighter. Original SVG; a mask wipe reveals it
 *  where view timelines exist, and the list beside it is the text equivalent. */
export function FrameworksRing() {
  const t = useTranslations("landing.ring");
  const r0 = 52;
  return <figure className="frameworks-ring" aria-label={t("label")}>
    <svg viewBox="0 0 400 400" aria-hidden="true" className="ring-art">
      {RINGS.map((name, i) => {
        const r = r0 + 28 * (i + 1);
        return <g key={name}>
          <circle cx="200" cy="200" r={r} className={i === 0 ? "ring ring-lead" : "ring"} />
          <text x="200" y={200 - r + 18} textAnchor="middle" className={i === 0 ? "ring-label ring-label-lead" : "ring-label"}>{name}</text>
        </g>;
      }).reverse()}
      <circle cx="200" cy="200" r={r0} className="ring-core" />
      <text x="200" y="196" textAnchor="middle" className="ring-core-label">{t("center").split(" ")[0]}</text>
      <text x="200" y="214" textAnchor="middle" className="ring-core-label">{t("center").split(" ").slice(1).join(" ")}</text>
    </svg>
    <figcaption className="ring-text"><p>{t("text")}</p><ul>{RINGS.map((name) => <li key={name}>{name}</li>)}</ul></figcaption>
  </figure>;
}
