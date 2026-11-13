"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { useChangeRole, useMembers, useRemoveMember } from "@/lib/api/hooks";
import type { Membership } from "@/lib/org";
import { ROLES, type Role, canChangeRoles, canRemove } from "@/lib/permissions";
import { useMe } from "./auth-gate";
import { ErrorMessage } from "./error-message";

export function MembersView({ org }: { org: Membership }) {
  const t = useTranslations();
  const me = useMe();
  const list = useMembers(org.organization_id);
  const changeRole = useChangeRole(org.organization_id);
  const remove = useRemoveMember(org.organization_id);
  const [confirming, setConfirming] = useState<string | null>(null);

  if (list.isPending) return <p role="status">{t("app.loading")}</p>;
  if (list.isError) return <ErrorMessage error={list.error} />;
  const failure = changeRole.error ?? remove.error;

  return (
    <section className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">{t("members.title", { org: org.organization_name })}</h1>
      {failure ? <ErrorMessage error={failure} /> : null}
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
              <td className="py-2 pr-4">
                <span>{m.email}</span>
                {m.display_name ? <span className="ml-2 text-muted">{m.display_name}</span> : null}
                {m.user_id === me.id ? <span className="ml-2 text-sm text-muted">{t("members.you")}</span> : null}
              </td>
              <td className="py-2 pr-4">
                {canChangeRoles(org.role) ? (
                  <select
                    aria-label={t("members.roleOf", { email: m.email })}
                    value={m.role}
                    disabled={changeRole.isPending}
                    onChange={(event) => changeRole.mutate({ userId: m.user_id, role: event.target.value as Role })}
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
              </td>
              <td className="py-2">
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
    </section>
  );
}
