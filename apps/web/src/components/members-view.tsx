"use client";

import { useFormatter, useTranslations } from "next-intl";
import { LoadError, Loading, PageHeader, Panel } from "./page-frame";
import { orgHome as homeOf } from "@/lib/org";
import { useState } from "react";
import { useChangeRole, useMembers, useRemoveMember } from "@/lib/api/hooks";
import type { Membership } from "@/lib/org";
import { ROLES, type Role, auditorWindow, canChangeRoles, canRemove } from "@/lib/permissions";
import { useMe } from "./auth-gate";
import { ErrorMessage } from "./error-message";

export function MembersView({ org }: { org: Membership }) {
  const t = useTranslations();
  const me = useMe();
  const list = useMembers(org.organization_id);
  const changeRole = useChangeRole(org.organization_id);
  const remove = useRemoveMember(org.organization_id);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [auditorFor, setAuditorFor] = useState<string | null>(null); // the end date comes first
  const format = useFormatter();
  const range = auditorWindow();

  const header = <PageHeader crumbs={[{ label: org.organization_name, href: homeOf(org.organization_id) }, { label: t("org.members") }]}
    title={t("members.title", { org: org.organization_name })} description={t("org.membersHelp")} />;
  if (list.isPending) return <>{header}<Loading /></>;
  if (list.isError) return <>{header}<LoadError error={list.error} onRetry={() => void list.refetch()} /></>;
  const failure = changeRole.error ?? remove.error;

  return (
    <>
      {header}
      {failure ? <ErrorMessage error={failure} /> : null}
      <Panel>
      <div className="table-region" role="region" aria-label={t("members.title", { org: org.organization_name })} tabIndex={0}>
      <table className="w-full text-left">
        <thead className="text-sm text-muted">
          <tr>
            <th scope="col">{t("members.member")}</th>
            <th scope="col">{t("members.role")}</th>
            <th scope="col">{t("members.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {list.data.map((m) => (
            <tr key={m.user_id} className="border-t border-border">
              <td data-label={t("members.member")} className="py-2 pr-4">
                <span>{m.email}</span>
                {m.display_name ? <span className="ml-2 text-muted">{m.display_name}</span> : null}
                {m.user_id === me.id ? <span className="ml-2 text-sm text-muted">{t("members.you")}</span> : null}
              </td>
              <td data-label={t("members.role")} className="py-2 pr-4">
                {canChangeRoles(org.role) ? (
                  <select
                    aria-label={t("members.roleOf", { email: m.email })}
                    value={auditorFor === m.user_id ? "auditor" : m.role}
                    disabled={changeRole.isPending}
                    onChange={(event) => {
                      const role = event.target.value as Role;
                      if (role === "auditor") { setAuditorFor(m.user_id); return; }
                      setAuditorFor(null);
                      changeRole.mutate({ userId: m.user_id, role });
                    }}
                    className="rounded-md border border-border bg-bg px-2 py-1"
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {t(`roles.${role}`)}
                      </option>
                    ))}
                  </select>
                ) : (
                  t(`roles.${m.role}`)
                )}
                {auditorFor === m.user_id ? (
                  <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={(event) => {
                    event.preventDefault();
                    const until = String(new FormData(event.currentTarget).get("until") ?? "");
                    changeRole.mutate({ userId: m.user_id, role: "auditor", accessExpiresOn: until }, { onSuccess: () => setAuditorFor(null) });
                  }}>
                    <label className="flex flex-col gap-1 text-sm">{t("members.accessUntil", { email: m.email })}
                      <input name="until" type="date" required min={range.min} max={range.max} className="rounded-md border border-border bg-bg px-2 py-1" />
                    </label>
                    <button type="submit" disabled={changeRole.isPending} className="rounded-md bg-accent px-3 py-1 text-accent-fg">{t("members.apply")}</button>
                    <button type="button" onClick={() => setAuditorFor(null)} className="underline">{t("members.cancel")}</button>
                  </form>
                ) : m.access_expires_on ? (
                  <span className="ml-2 text-sm text-muted">
                    {t("members.accessOn", { date: format.dateTime(new Date(`${m.access_expires_on}T00:00:00Z`), { dateStyle: "medium", timeZone: "UTC" }) })}
                  </span>
                ) : null}
              </td>
              <td data-label={t("members.actions")} className="py-2">
                {!canRemove(org.role, m.role) ? null : confirming === m.user_id ? (
                  <span className="flex flex-wrap items-center gap-2">
                    <span>{t("members.confirmRemove", { email: m.email })}</span>
                    <button
                      type="button"
                      onClick={() => remove.mutate(m.user_id, { onSettled: () => setConfirming(null) })}
                      className="rounded-md bg-danger px-3 py-1 text-danger-fg"
                    >
                      {t("members.confirm")}
                    </button>
                    <button type="button" onClick={() => setConfirming(null)} className="underline">
                      {t("members.cancel")}
                    </button>
                  </span>
                ) : (
                  <button type="button" onClick={() => setConfirming(m.user_id)} className="underline">
                    {t("members.remove")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      </Panel>
    </>
  );
}
