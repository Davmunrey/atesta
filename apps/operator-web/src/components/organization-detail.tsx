"use client";

import { useSearchParams } from "next/navigation";
import { useFormatter, useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { Badge } from "@atesta/ui/badge";
import { Fact, Facts } from "@atesta/ui/facts";
import { LoadError, Loading, PageHeader, Panel } from "@atesta/ui/page-frame";
import { type OrganizationDetail, useOrganization } from "@/lib/api/organizations";
import Link from "next/link";
import { canBill } from "@/lib/roles";
import { AddonName, HealthBadge, PlanName, StateBadge } from "./organization-labels";
import { useStaff } from "./portal-shell";

/** Screen 3 of the operator-portal spec: every metadata field, grouped; never content. */
export function OrganizationDetailPage() {
  const t = useTranslations("organization");
  const list = useTranslations("organizations");
  const id = useSearchParams().get("id") ?? "";
  const query = useOrganization(id);
  const crumbs = [{ label: list("title"), href: "/" }, { label: query.data?.name ?? t("crumb") }];
  if (query.isPending) return <><PageHeader crumbs={crumbs} title={t("crumb")} /><Loading /></>;
  if (query.isError) return <><PageHeader crumbs={crumbs} title={t("crumb")} /><LoadError error={query.error} onRetry={() => void query.refetch()} /></>;
  const org = query.data;
  return <>
    <PageHeader crumbs={crumbs} title={org.name} description={<StateBadge state={org.state} />} />
    <div className="panel-grid panel-grid-halves">
      <Overview org={org} />
      <State org={org} />
      <Plan org={org} />
      <Billing org={org} />
      <Usage org={org} />
      <Connections org={org} />
    </div>
  </>;
}

type Props = { org: OrganizationDetail };
const PROVIDERS = ["m365", "google_workspace"];
const useDate = () => {
  const format = useFormatter();
  return (iso: string) => format.dateTime(new Date(iso), { dateStyle: "long" });
};
/** Counts by key as one line: "2 propietarios, 1 auditor"; `none` when there is nothing. */
function Counts({ counts, label, none }: { counts: Record<string, number>; label: (key: string, count: number) => string; none: ReactNode }) {
  const entries = Object.entries(counts).filter(([, n]) => n > 0);
  return <>{entries.length === 0 ? none : entries.map(([key, n]) => label(key, n)).join(", ")}</>;
}

function Overview({ org }: Props) {
  const t = useTranslations("organization");
  const date = useDate();
  return <Panel title={t("overview")}><Facts>
    <Fact label={t("id")}><span className="font-mono">{org.id}</span></Fact>
    <Fact label={t("language")}>{t(`languages.${org.locale === "en" ? "en" : "es"}`)}</Fact>
    <Fact label={t("created")}>{date(org.created_at)}</Fact>
    <Fact label={t("trial")}>{org.plan.default ? t(org.trial_ended ? "trialEnded" : "trialEnds", { date: date(org.trial_ends_at) }) : t("trialOver")}</Fact>
    <Fact label={t("lastActivity")}>{org.last_activity ? date(org.last_activity) : t("never")}</Fact>
  </Facts></Panel>;
}

function State({ org }: Props) {
  const t = useTranslations("organization");
  const date = useDate();
  return <Panel title={t("state")}><Facts>
    <Fact label={t("state")}><StateBadge state={org.state} /></Fact>
    {org.suspended_at ? <Fact label={t("suspendedSince")}>{date(org.suspended_at)}</Fact> : null}
    {org.suspension_reason ? <Fact label={t("suspensionReason")}>{t(`reasons.${org.suspension_reason}`)}</Fact> : null}
    {org.closure ? <>
      <Fact label={t("closureStarted")}>{t("closureBy", { date: date(org.closure.requested_at), origin: org.closure.origin })}</Fact>
      <Fact label={t("eraseAfter")}>{date(org.closure.erase_after)}</Fact>
    </> : null}
    {org.erasure ? <Fact label={t("erasure")}>{t(`erasureStates.${org.erasure.state}`)}</Fact> : null}
  </Facts></Panel>;
}

/** The way to an action, shown only to the roles that may take it (spec, screen 3). */
function Action({ href, label }: { href: string; label: string }) {
  return canBill(useStaff().role) ? <Link href={href} className="dashboard-button action-link">{label}</Link> : null;
}

function Plan({ org }: Props) {
  const t = useTranslations("organization");
  const date = useDate();
  return <Panel title={t("plan")} actions={<Action href={`/organization/plan?id=${org.id}`} label={t("changePlan")} />}><Facts>
    <Fact label={t("plan")}><PlanName plan={org.plan.plan} isDefault={org.plan.default} /></Fact>
    <Fact label={t("addons")}>{org.plan.addons?.length ? org.plan.addons.map((a, i) => <span key={a}>{i > 0 ? ", " : null}<AddonName addon={a} /></span>) : t("noAddons")}</Fact>
    {org.plan.note ? <Fact label={t("note")}>{org.plan.note}</Fact> : null}
    {org.plan.updated_at ? <Fact label={t("planSet")}>{date(org.plan.updated_at)}</Fact> : null}
  </Facts></Panel>;
}

function Billing({ org }: Props) {
  const t = useTranslations("organization");
  const b = org.billing;
  return <Panel title={t("billing")} actions={<Action href={`/organization/billing?id=${org.id}`} label={t("editBilling")} />}>{b === null ? <p className="state-empty">{t("noBilling")}</p> : <Facts>
    <Fact label={t("billingState")}>{b.complete ? <Badge state="billingComplete">{t("complete")}</Badge> : <Badge state="billingMissing">{t("incomplete")}</Badge>}</Fact>
    <Fact label={t("legalName")}>{b.legal_name ?? t("notRecorded")}</Fact>
    {b.view === "full" ? <>
      <Fact label={t("taxId")}><span className="font-mono">{b.tax_id ?? t("notRecorded")}</span></Fact>
      <Fact label={t("address")}>{[b.address_line1, b.address_line2, b.postal_code, b.city, b.region, b.country].filter(Boolean).join(", ") || t("notRecorded")}</Fact>
      <Fact label={t("contactEmail")}>{b.contact_email ?? t("notRecorded")}</Fact>
    </> : null}
  </Facts>}</Panel>;
}

function Usage({ org }: Props) {
  const t = useTranslations("organization");
  const date = useDate();
  return <Panel title={t("usage")}><Facts>
    <Fact label={t("members")}><Counts counts={org.members} none={t("none")} label={(role, count) => t(`roles.${role}`, { count })} /></Fact>
    <Fact label={t("invitations")}>{t("count", { count: org.pending_invitations })}</Fact>
    <Fact label={t("scans")}><Counts counts={org.scans.last_30_days} none={t("none")} label={(status, count) => t(`scanStates.${status}`, { count })} /></Fact>
    <Fact label={t("lastScan")}>{org.scans.last_finished ? date(org.scans.last_finished) : t("never")}</Fact>
    <Fact label={t("apiKeys")}>{t("count", { count: org.api_keys })}</Fact>
    <Fact label={t("apiCalls")}>{t("count", { count: org.api_calls_30_days })}</Fact>
  </Facts></Panel>;
}

function Connections({ org }: Props) {
  const t = useTranslations("organization");
  const c = org.connections;
  return <Panel title={t("connections")}><Facts>
    <Fact label={t("health")}><HealthBadge health={c.health} /></Fact>
    <Fact label={t("inUse")}>{c.limit === null ? t("inUseNoLimit", { count: c.in_use }) : t("inUseOf", { count: c.in_use, limit: c.limit })}</Fact>
    {Object.entries(c.by_provider).map(([provider, statuses]) => <Fact key={provider} label={PROVIDERS.includes(provider) ? t(`providers.${provider}`) : provider}>
      <Counts counts={statuses} none={t("none")} label={(status, count) => t(`connectionStates.${status}`, { count })} />
    </Fact>)}
  </Facts></Panel>;
}
