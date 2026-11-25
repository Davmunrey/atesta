"use client";

import { usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { type ReactNode, createContext, use } from "react";
import { ApiError } from "@atesta/ui/api-error";
import { AccountMenu, AppShell, type NavGroup } from "@atesta/ui/app-shell";
import { LOGOUT_URL, loginUrl } from "@atesta/ui/auth";
import { isLocale } from "@atesta/ui/i18n/locale";
import { LocaleSwitcher } from "@atesta/ui/locale-switcher";
import { Empty, LoadError, Loading, PageHeader } from "@atesta/ui/page-frame";
import { useMeQuery } from "@/lib/api/hooks";
import { type Staff, isAdmin } from "@/lib/roles";

export const StaffContext = createContext<Staff | null>(null);

export function useStaff(): Staff {
  const staff = use(StaffContext);
  if (staff === null) throw new Error("useStaff outside PortalShell");
  return staff;
}

// A detail page lights up its list in the menu.
const SECTION: Record<string, string> = { "/organization": "/", "/organization/plan": "/", "/organization/billing": "/" };

function useNavigation(staff: Staff | undefined): NavGroup[] | null {
  const t = useTranslations("portal.nav");
  if (!staff) return null;
  const admin = isAdmin(staff.role);
  return [
    { group: t("customers"), items: [
      { key: "/", label: t("organizations"), href: "/", icon: "home" as const },
      ...(admin ? [{ key: "/erased", label: t("erased"), href: "/erased", icon: "notApplicable" as const }] : []),
    ] },
    ...(admin ? [{ group: t("admin"), items: [
      { key: "/team", label: t("team"), href: "/team", icon: "members" as const },
      { key: "/log", label: t("log"), href: "/log", icon: "activity" as const },
    ] }] : []),
  ];
}

/** The operator portal's frame (operator-portal spec, screen 1): the shared shell named "Portal de
 *  operaciones", navigation by role from `GET /me`; signed out, the sign-in page; no access, why. */
export function PortalShell({ children }: { children: ReactNode }) {
  const t = useTranslations("portal");
  const role = useTranslations("portal.role");
  const me = useMeQuery();
  const pathname = usePathname().replace(/\/$/, "") || "/";
  const nav = useNavigation(me.data);
  const status = me.error instanceof ApiError ? me.error.status : null;
  return <AppShell home="/" label={{ full: t("name"), short: t("shortName") }} nav={nav} navLabel={t("nav.label")} current={SECTION[pathname] ?? pathname}
    end={<><LocaleSwitcher compact />
      {me.data ? <AccountMenu email={me.data.email} signOutHref={LOGOUT_URL}>
        <p className="account-email"><span className="text-muted">{role("label")}</span> {role(me.data.role)}</p>
      </AccountMenu> : null}</>}>
    {me.data ? <StaffContext value={me.data}>{children}</StaffContext>
      : status === 401 ? <SignIn />
      : status === 403 ? <NoAccess />
      : me.error ? <LoadError error={me.error} onRetry={() => void me.refetch()} />
      : <Loading />}
  </AppShell>;
}

/** Signed out: the staff pool's managed login, then back to the page asked for. */
function SignIn() {
  const t = useTranslations("portal.signIn");
  const locale = useLocale();
  const back = typeof window === "undefined" ? "/" : window.location.pathname + window.location.search;
  return <>
    <PageHeader title={t("title")} description={t("body")} />
    <a href={loginUrl(isLocale(locale) ? locale : "es", back)} className="button-primary action-link">{t("action")}</a>
  </>;
}

/** A valid staff sign-in without an enabled staff row (403 `operator.forbidden`). */
function NoAccess() {
  const t = useTranslations("portal.noAccess");
  const app = useTranslations("app");
  return <>
    <PageHeader title={t("title")} />
    <Empty>{t("body")}</Empty>
    <a href={LOGOUT_URL} className="dashboard-button action-link">{app("signOut")}</a>
  </>;
}
