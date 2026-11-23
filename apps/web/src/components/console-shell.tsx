"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useFormatter, useLocale, useTranslations } from "next-intl";
import { type ReactNode, useDeferredValue, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { useOverview } from "@/lib/api/hooks";
import { useSearch } from "@/lib/api/register-hooks";
import { LOGOUT_URL } from "@/lib/auth";
import { type Membership, orgAccessReviews, orgActivity, orgFramework, orgFrameworks, orgHome, orgInvitations, orgMembers, orgIncidents, orgIntegrations, orgMyWork, orgPolicies, orgReport, orgSettings, orgTraining, selectOrg } from "@/lib/org";
import { canInvite, canReviewControls, isContributor } from "@/lib/permissions";
import { useMe } from "./auth-gate";
import { Icon, type IconName } from "./icons";
import { LocaleSwitcher } from "./locale-switcher";
import { SiteFooter } from "./site-footer";

// A detail page lights up its list in the menu.
const DETAIL_PAGES: Record<string, string> = {
  "/app/framework": "/app/frameworks",
  "/app/dossier": "/app/frameworks",
  "/app/access-review": "/app/access-reviews",
  "/app/training-campaign": "/app/training-campaigns",
  "/app/incident": "/app/incidents",
};
const ORG_PAGES = ["/app/org", "/app/framework", "/app/frameworks", "/app/members", "/app/invitations", "/app/activity", "/app/my-work", "/app/settings", "/app/access-reviews", "/app/access-review", "/app/policies", "/app/training-campaigns", "/app/training-campaign", "/app/incidents", "/app/incident", "/app/integrations", "/app/dossier", "/app/report"];
const DESKTOP = "(min-width: 64rem)";

// The collapsed rail is a remembered preference; media and storage are read as external stores.
const listeners = new Set<() => void>();
const subscribeNav = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };
const readCollapsed = () => localStorage.getItem("atesta_nav") === "collapsed";
function setCollapsed(value: boolean) {
  localStorage.setItem("atesta_nav", value ? "collapsed" : "expanded");
  for (const l of listeners) l();
}
// Without matchMedia (old engines, tests) the console behaves as on a desktop.
const hasMedia = () => typeof window !== "undefined" && typeof window.matchMedia === "function";
const subscribeMedia = (l: () => void) => {
  if (!hasMedia()) return () => {};
  const m = window.matchMedia(DESKTOP); m.addEventListener("change", l); return () => m.removeEventListener("change", l);
};
const isDesktop = () => !hasMedia() || window.matchMedia(DESKTOP).matches;

type Section = { key: string; label: string; href: string; icon: IconName };

export function useSections(org: Membership | null): { group: string; items: Section[] }[] {
  const t = useTranslations("org");
  const c = useTranslations("console");
  if (!org) return [];
  const id = org.organization_id;
  const groups = [
    { group: c("groups.general"), items: [
      { key: "/app/org", label: t("overview"), href: orgHome(id), icon: "home" as const },
      ...(isContributor(org.role) ? [{ key: "/app/my-work", label: t("myWork"), href: orgMyWork(id), icon: "work" as const }] : []),
      { key: "/app/frameworks", label: c("frameworks"), href: orgFrameworks(id), icon: "frameworks" as const },
      { key: "/app/report", label: c("report"), href: orgReport(id), icon: "report" as const },
    ] },
    { group: c("groups.records"), items: [
      { key: "/app/access-reviews", label: c("accessReviews"), href: orgAccessReviews(id), icon: "reviews" as const },
      { key: "/app/policies", label: c("policies"), href: orgPolicies(id), icon: "policies" as const },
      { key: "/app/training-campaigns", label: c("training"), href: orgTraining(id), icon: "training" as const },
      { key: "/app/incidents", label: c("incidents"), href: orgIncidents(id), icon: "incidents" as const },
    ] },
    { group: c("groups.team"), items: [
      ...(isContributor(org.role) ? [{ key: "/app/members", label: t("members"), href: orgMembers(id), icon: "members" as const }] : []),
      ...(canInvite(org.role) ? [{ key: "/app/invitations", label: t("invitations"), href: orgInvitations(id), icon: "invitations" as const }] : []),
    ] },
    { group: c("groups.oversight"), items: canReviewControls(org.role) ? [{ key: "/app/activity", label: t("activity"), href: orgActivity(id), icon: "activity" as const }] : [] },
    { group: c("groups.organization"), items: [
      ...(canReviewControls(org.role) ? [{ key: "/app/integrations", label: c("integrations"), href: orgIntegrations(id), icon: "integrations" as const }] : []),
      ...(org.role === "owner" ? [{ key: "/app/settings", label: t("settings"), href: orgSettings(id), icon: "settings" as const }] : []),
    ] },
  ];
  return groups.filter((g) => g.items.length > 0);
}

/** The console frame (console-shell spec): top bar, grouped side navigation, notices, page. */
export function ConsoleShell({ children }: { children: ReactNode }) {
  const c = useTranslations("console");
  const brand = useTranslations("brand");
  const { memberships } = useMe();
  const pathname = usePathname();
  const org = selectOrg(memberships, useSearchParams().get("org"));
  const inOrg = org !== null && ORG_PAGES.includes(pathname);
  const collapsed = useSyncExternalStore(subscribeNav, readCollapsed, () => false);
  const desktop = useSyncExternalStore(subscribeMedia, isDesktop, () => true);
  const [drawer, setDrawer] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const navId = useId();
  const closeDrawer = () => { setDrawer(false); menuButton.current?.focus(); };
  const expanded = desktop ? !collapsed : drawer;
  return <div className="console" data-nav={inOrg ? (collapsed ? "collapsed" : "expanded") : "none"} data-drawer={drawer ? "open" : "closed"}>
    <a href="#main-content" className="skip-link">{c("skip")}</a>
    <header className="topbar">
      {inOrg ? <button ref={menuButton} type="button" className="topbar-icon" aria-controls={navId} aria-expanded={expanded}
        aria-label={c(expanded ? "menuHide" : "menuShow")} title={c(expanded ? "menuHide" : "menuShow")}
        onClick={() => (desktop ? setCollapsed(!collapsed) : setDrawer(!drawer))}>
        <Icon name="menu" />
      </button> : null}
      <Link href="/app" className="topbar-brand">{brand("name")}</Link>
      {org && inOrg ? <OrgSwitcher org={org} memberships={memberships} /> : null}
      {org && inOrg ? <GlobalSearch org={org} /> : <span className="topbar-spacer" />}
      <div className="topbar-end"><LocaleSwitcher compact /><AccountMenu /></div>
    </header>
    <div className="console-body">
      {org && inOrg ? <SideNav id={navId} org={org} pathname={pathname} collapsed={desktop && collapsed} onNavigate={() => !desktop && setDrawer(false)} onEscape={closeDrawer} /> : null}
      {/* Pointer-only backdrop: keyboards close the drawer with Esc or the menu button. */}
      {drawer && !desktop ? <div className="drawer-scrim" aria-hidden="true" onClick={closeDrawer} /> : null}
      <div className="console-main">
        {org && inOrg ? <Notices org={org} /> : null}
        <main id="main-content" tabIndex={-1} className="console-page">{children}</main>
        <SiteFooter />
      </div>
    </div>
  </div>;
}

function SideNav({ id, org, pathname, collapsed, onNavigate, onEscape }: { id: string; org: Membership; pathname: string; collapsed: boolean; onNavigate: () => void; onEscape: () => void }) {
  const t = useTranslations("org");
  const groups = useSections(org);
  const current = DETAIL_PAGES[pathname] ?? pathname;
  return <nav id={id} aria-label={t("sections")} className="sidenav" data-collapsed={collapsed ? "true" : "false"}
    onKeyDown={(e) => { if (e.key === "Escape") onEscape(); }}>
    {groups.map(({ group, items }) => <div key={group} className="sidenav-group">
      <p className="sidenav-label" aria-hidden={collapsed}>{group}</p>
      <ul>{items.map((s) => <li key={s.key}>
        <Link href={s.href} aria-current={s.key === current ? "page" : undefined} title={collapsed ? s.label : undefined} onClick={onNavigate}>
          <Icon name={s.icon} /><span className="sidenav-text">{s.label}</span>
        </Link>
      </li>)}</ul>
    </div>)}
  </nav>;
}

function OrgSwitcher({ org, memberships }: { org: Membership; memberships: Membership[] }) {
  const t = useTranslations("org");
  const router = useRouter();
  const pathname = usePathname();
  const id = useId();
  if (memberships.length < 2) return <span className="topbar-org">{org.organization_name}</span>;
  function switchTo(next: string) {
    const target = selectOrg(memberships, next);
    if (!target) return;
    const destination = pathname === "/app/members" && isContributor(target.role) ? orgMembers
      : pathname === "/app/my-work" && isContributor(target.role) ? orgMyWork
      : pathname === "/app/invitations" && canInvite(target.role) ? orgInvitations
      : pathname === "/app/frameworks" ? orgFrameworks : orgHome;
    router.push(destination(next));
  }
  return <span className="topbar-org">
    <label htmlFor={id} className="sr-only">{t("switcher")}</label>
    <select id={id} value={org.organization_id} onChange={(e) => switchTo(e.target.value)} className="topbar-select">
      {memberships.map((m) => <option key={m.organization_id} value={m.organization_id}>{m.organization_name}</option>)}
    </select>
  </span>;
}

function Notices({ org }: { org: Membership }) {
  const t = useTranslations("org");
  const format = useFormatter();
  if (!org.access_expires_on && !org.closure_erase_after) return null;
  return <div className="notices">
    {org.access_expires_on ? <p className="notice" role="note"><Icon name="pending" />
      {t("auditorUntil", { date: format.dateTime(new Date(`${org.access_expires_on}T00:00:00Z`), { dateStyle: "long", timeZone: "UTC" }) })}</p> : null}
    {org.closure_erase_after ? <p className="notice" data-severity="overdue" role="note"><Icon name="overdue" />
      {t("closing", { date: format.dateTime(new Date(org.closure_erase_after), { dateStyle: "long" }) })}</p> : null}
  </div>;
}

type Result = { id: string; group: "pages" | "frameworks" | "measures"; label: string; detail?: string; href: string; lang?: string };

/** Global search (console-shell spec): an ARIA 1.2 combobox over pages, frameworks and measures. */
function GlobalSearch({ org }: { org: Membership }) {
  const c = useTranslations("console");
  const english = useLocale() === "en";
  const router = useRouter();
  const sections = useSections(org).flatMap((g) => g.items);
  const overview = useOverview(org.organization_id);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const deferred = useDeferredValue(query.trim());
  const measures = useSearch(org.organization_id, deferred);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  useEffect(() => {
    const focus = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.current?.focus(); }
    };
    document.addEventListener("keydown", focus);
    return () => document.removeEventListener("keydown", focus);
  }, []);
  const needle = deferred.toLocaleLowerCase();
  const results: Result[] = needle.length < 2 ? [] : [
    ...sections.filter((s) => s.label.toLocaleLowerCase().includes(needle)).map((s) => ({ id: `p:${s.key}`, group: "pages" as const, label: s.label, href: s.href })),
    ...(overview.data?.frameworks ?? []).filter((f) => f.name.toLocaleLowerCase().includes(needle))
      .map((f) => ({ id: `f:${f.key}`, group: "frameworks" as const, label: f.name, href: orgFramework(org.organization_id, f.key) })),
    ...(measures.data ?? []).map((m) => ({
      id: `m:${m.framework_key}:${m.code}`, group: "measures" as const, label: english ? m.title_en ?? m.title_es : m.title_es,
      lang: english && !m.title_en ? "es" : undefined, detail: `${m.code} · ${m.framework_name}`,
      href: `${orgFramework(org.organization_id, m.framework_key)}#req-${encodeURIComponent(m.code)}`,
    })),
  ];
  const shown = open && needle.length >= 2;
  const current = Math.min(active, Math.max(results.length - 1, 0));
  function go(result: Result | undefined) {
    if (!result) return;
    setOpen(false); setQuery("");
    router.push(result.href);
  }
  return <div className="topbar-search" role="search">
    <Icon name="search" className="topbar-search-icon" />
    <input ref={input} type="search" role="combobox" aria-label={c("searchLabel")} placeholder={c("searchPlaceholder")}
      aria-expanded={shown} aria-controls={listId} aria-autocomplete="list"
      aria-activedescendant={shown && results[current] ? `${listId}-${current}` : undefined}
      value={query} onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }} onFocus={() => setOpen(true)}
      onBlur={() => setTimeout(() => setOpen(false), 150)}
      onKeyDown={(e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); setActive(Math.min(current + 1, results.length - 1)); }
        else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(current - 1, 0)); }
        else if (e.key === "Enter") { e.preventDefault(); go(results[current]); }
        else if (e.key === "Escape") { setQuery(""); setOpen(false); }
      }} />
    <kbd className="topbar-kbd" aria-hidden="true">⌘K</kbd>
    <ul id={listId} role="listbox" aria-label={c("searchLabel")} className="search-results" hidden={!shown}>
      {results.length === 0 ? <li role="option" aria-selected="false" aria-disabled="true" className="search-empty">
        {measures.isFetching ? c("searching") : c("noResults")}</li>
        : results.map((r, i) => <li key={r.id} id={`${listId}-${i}`} role="option" aria-selected={i === current}
          onMouseDown={(e) => { e.preventDefault(); go(r); }} onMouseEnter={() => setActive(i)}>
          <span className="search-group">{c(`results.${r.group}`)}</span>
          <span className="search-label" lang={r.lang}>{r.label}</span>
          {r.detail ? <span className="search-detail">{r.detail}</span> : null}
        </li>)}
    </ul>
  </div>;
}

function AccountMenu() {
  const t = useTranslations("app");
  const me = useMe();
  const id = useId();
  const initial = (me.email.trim()[0] ?? "?").toLocaleUpperCase();
  return <>
    <button type="button" className="account-trigger" popoverTarget={id} aria-label={t("account")} title={me.email}>
      <span aria-hidden="true">{initial}</span>
    </button>
    <div id={id} popover="auto" className="account-menu" aria-label={t("account")}>
      <p className="account-email"><span className="text-muted">{t("signedInLabel")}</span> <strong>{me.email}</strong></p>
      <a href={LOGOUT_URL} className="account-signout">{t("signOut")}</a>
    </div>
  </>;
}
