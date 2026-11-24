"use client";

import { useTranslations } from "next-intl";
import { useId } from "react";
import { type Kind, type Preference, useChangePreference, usePreferences } from "@/lib/api/notifications";
import { type Membership, orgHome } from "@/lib/org";
import { ErrorMessage } from "./error-message";
import { LoadError, Loading, PageHeader, Panel } from "./page-frame";

/** A person's email notices in one organization (notifications spec PR 1, issue 379). */
export function NotificationsView({ org }: { org: Membership }) {
  const t = useTranslations("notifications");
  const prefs = usePreferences(org.organization_id);
  const change = useChangePreference(org.organization_id);
  return <div className="panel-grid">
    <PageHeader crumbs={[{ label: org.organization_name, href: orgHome(org.organization_id) }, { label: t("title") }]}
      title={t("title")} description={t("intro", { org: org.organization_name })} />
    <p className="notice" role="status">{t("notYetSending")}</p>
    <Panel title={t("types")}>
      {prefs.isPending ? <Loading label={t("loading")} /> : prefs.isError ? <LoadError error={prefs.error} onRetry={() => void prefs.refetch()} />
        : <ul className="preference-list">{prefs.data.map((p) =>
          <Row key={p.kind} preference={p} busy={change.isPending} onChange={(enabled) => change.mutate({ kind: p.kind, enabled })} />)}</ul>}
      {change.isError ? <ErrorMessage error={change.error} /> : null}
    </Panel>
  </div>;
}

function Row({ preference: p, busy, onChange }: { preference: Preference; busy: boolean; onChange: (enabled: boolean) => void }) {
  const t = useTranslations("notifications");
  const id = useId();
  const kind: Kind = p.kind;
  return <li className="preference-row">
    <input id={id} type="checkbox" checked={p.enabled} disabled={!p.can_disable || busy}
      aria-describedby={`${id}-help`} onChange={(e) => onChange(e.currentTarget.checked)} />
    <span>
      <label htmlFor={id} className="font-medium">{t(`kinds.${kind}.name`)}</label>
      <span id={`${id}-help`} className="block text-sm text-muted">{t(`kinds.${kind}.help`)}
        {p.can_disable ? null : <span className="block">{t("locked")}</span>}</span>
    </span>
  </li>;
}
