"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { type ReactNode, useId, useRef, useState, useSyncExternalStore } from "react";
import { BrandMark } from "./brand-mark";
import { Icon, type IconName } from "./icons";

export type NavItem = { key: string; label: string; href: string; icon: IconName };
export type NavGroup = { group: string; items: NavItem[] };

const DESKTOP = "(min-width: 64rem)";

// The collapsed rail is a remembered preference; media and storage are read as external stores.
const listeners = new Set<() => void>();
const subscribeNav = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };
const readCollapsed = () => localStorage.getItem("atesta_nav") === "collapsed";
function setCollapsed(value: boolean) {
  localStorage.setItem("atesta_nav", value ? "collapsed" : "expanded");
  for (const l of listeners) l();
}
// Without matchMedia (old engines, tests) the shell behaves as on a desktop.
const hasMedia = () => typeof window !== "undefined" && typeof window.matchMedia === "function";
export const subscribeMedia = (l: () => void) => {
  if (!hasMedia()) return () => {};
  const m = window.matchMedia(DESKTOP); m.addEventListener("change", l); return () => m.removeEventListener("change", l);
};
export const isDesktop = () => !hasMedia() || window.matchMedia(DESKTOP).matches;

/**
 * The frame of every signed-in Atesta app (console-shell spec; ADR-017, "Design system"): the ink
 * top bar with the lockup, grouped side navigation (a rail on desktop, a drawer below), notices and
 * the page. Each app passes its own navigation, top-bar content and account menu. An app other than
 * the console names itself beside the lockup (`label`, with a short form for phones), so staff never
 * mistake it for the console
 * (ADR-017, "Environment marker").
 */
export function AppShell({ home, label, nav, navLabel, current, topbar, end, notices, footer, children }: {
  home: string; label?: { full: string; short: string }; nav: NavGroup[] | null; navLabel: string; current?: string;
  topbar?: ReactNode; end: ReactNode; notices?: ReactNode; footer?: ReactNode; children: ReactNode;
}) {
  const c = useTranslations("console");
  const brand = useTranslations("brand");
  const collapsed = useSyncExternalStore(subscribeNav, readCollapsed, () => false);
  const desktop = useSyncExternalStore(subscribeMedia, isDesktop, () => true);
  const [drawer, setDrawer] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const navId = useId();
  const closeDrawer = () => { setDrawer(false); menuButton.current?.focus(); };
  const expanded = desktop ? !collapsed : drawer;
  return <div className="console" data-nav={nav ? (collapsed ? "collapsed" : "expanded") : "none"} data-drawer={drawer ? "open" : "closed"}>
    <a href="#main-content" className="skip-link">{c("skip")}</a>
    <header className="topbar">
      {nav ? <button ref={menuButton} type="button" className="topbar-icon" aria-controls={navId} aria-expanded={expanded}
        aria-label={c(expanded ? "menuHide" : "menuShow")} title={c(expanded ? "menuHide" : "menuShow")}
        onClick={() => (desktop ? setCollapsed(!collapsed) : setDrawer(!drawer))}>
        <Icon name="menu" />
      </button> : null}
      <Link href={home} className="topbar-brand" aria-label={label ? `${brand("name")} · ${label.full}` : brand("name")}><BrandMark /><span>{brand("name")}</span></Link>
      {/* The full name, or its short form on a phone; the brand link already reads it out. */}
      {label ? <span className="topbar-label" aria-hidden="true"><span>{label.full}</span><span>{label.short}</span></span> : null}
      {topbar ?? <span className="topbar-spacer" />}
      <div className="topbar-end">{end}</div>
    </header>
    <div className="console-body">
      {nav ? <SideNav id={navId} label={navLabel} groups={nav} current={current} collapsed={desktop && collapsed}
        onNavigate={() => !desktop && setDrawer(false)} onEscape={closeDrawer} /> : null}
      {/* Pointer-only backdrop: keyboards close the drawer with Esc or the menu button. */}
      {drawer && !desktop ? <div className="drawer-scrim" aria-hidden="true" onClick={closeDrawer} /> : null}
      <div className="console-main">
        {notices}
        <main id="main-content" tabIndex={-1} className="console-page">{children}</main>
        {footer}
      </div>
    </div>
  </div>;
}

function SideNav({ id, label, groups, current, collapsed, onNavigate, onEscape }: {
  id: string; label: string; groups: NavGroup[]; current?: string; collapsed: boolean; onNavigate: () => void; onEscape: () => void;
}) {
  return <nav id={id} aria-label={label} className="sidenav" data-collapsed={collapsed ? "true" : "false"}
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

/** The account menu (workspace-ux spec): a quiet initial; who is signed in lives in the popover. */
export function AccountMenu({ email, signOutHref, children }: { email: string; signOutHref: string; children?: ReactNode }) {
  const t = useTranslations("app");
  const id = useId();
  const initial = (email.trim()[0] ?? "?").toLocaleUpperCase();
  return <>
    <button type="button" className="account-trigger" popoverTarget={id} aria-label={t("account")} title={email}>
      <span aria-hidden="true">{initial}</span>
    </button>
    <div id={id} popover="auto" className="account-menu" aria-label={t("account")}>
      <p className="account-email"><span className="text-muted">{t("signedInLabel")}</span> <strong>{email}</strong></p>
      {children}
      <a href={signOutHref} className="account-signout">{t("signOut")}</a>
    </div>
  </>;
}

/** A one-line notice under the top bar or in a page: icon plus text; `overdue` for what blocks. */
export function Notice({ severity, children }: { severity?: "overdue"; children: ReactNode }) {
  return <p className="notice" data-severity={severity} role="note"><Icon name={severity ?? "pending"} />{children}</p>;
}
