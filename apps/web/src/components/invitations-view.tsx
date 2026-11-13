"use client";

import { useFormatter, useTranslations } from "next-intl";
import { useId, useState } from "react";
import { useCreateInvitation, useInvitations, useRevokeInvitation } from "@/lib/api/hooks";
import type { Membership } from "@/lib/org";
import { type Role, invitableRoles } from "@/lib/permissions";
import { ErrorMessage } from "./error-message";

export function InvitationsView({ org }: { org: Membership }) {
  const t = useTranslations();
  const format = useFormatter();
  const id = useId();
  const list = useInvitations(org.organization_id);
  const create = useCreateInvitation(org.organization_id);
  const revoke = useRevokeInvitation(org.organization_id);
  const [confirming, setConfirming] = useState<string | null>(null);

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    create.mutate(
      { email: String(data.get("email") ?? "").trim(), role: data.get("role") as Role },
      { onSuccess: () => form.reset() },
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">{t("invitations.title", { org: org.organization_name })}</h1>
      <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
        <span className="flex flex-col gap-1">
          <label htmlFor={`${id}-email`}>{t("invitations.email")}</label>
          <input id={`${id}-email`} name="email" type="email" required maxLength={320} className="rounded-md border border-border bg-bg px-3 py-2" />
        </span>
        <span className="flex flex-col gap-1">
          <label htmlFor={`${id}-role`}>{t("invitations.role")}</label>
          <select id={`${id}-role`} name="role" defaultValue="member" className="rounded-md border border-border bg-bg px-2 py-2">
            {invitableRoles(org.role).map((role) => (
              <option key={role} value={role}>
                {t(`roles.${role}`)}
              </option>
            ))}
          </select>
        </span>
        <button type="submit" disabled={create.isPending} className="rounded-md bg-accent px-4 py-2 font-medium text-accent-fg">
          {t("invitations.invite")}
        </button>
      </form>
      {create.isError ? <ErrorMessage error={create.error} /> : null}
      {create.data ? <CreatedLink email={create.data.email} link={create.data.accept_link} /> : null}

      <h2 className="text-lg font-semibold">{t("invitations.pending")}</h2>
      {revoke.isError ? <ErrorMessage error={revoke.error} /> : null}
      {list.isPending ? (
        <p role="status">{t("app.loading")}</p>
      ) : list.isError ? (
        <ErrorMessage error={list.error} />
      ) : list.data.length === 0 ? (
        <p className="text-muted">{t("invitations.none")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {list.data.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-3 border-t border-border pt-2">
              <span>{i.email}</span>
              <span className="text-sm text-muted">{t(`roles.${i.role}`)}</span>
              <span className="text-sm text-muted">
                {t("invitations.expires", { date: format.dateTime(new Date(i.expires_at), { dateStyle: "medium" }) })}
              </span>
              {confirming === i.id ? (
                <span className="flex gap-2">
                  <button type="button" onClick={() => revoke.mutate(i.id, { onSettled: () => setConfirming(null) })} className="rounded-md bg-danger px-3 py-1 text-danger-fg">
                    {t("members.confirm")}
                  </button>
                  <button type="button" onClick={() => setConfirming(null)} className="underline">
                    {t("members.cancel")}
                  </button>
                </span>
              ) : (
                <button type="button" onClick={() => setConfirming(i.id)} className="underline">
                  {t("invitations.revoke")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The API keeps only a hash of the token: this is the only time the link exists in full. */
function CreatedLink({ email, link }: { email: string; link: string }) {
  const t = useTranslations("invitations");
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-surface p-4">
      <p>{t("created", { email })}</p>
      <p className="font-medium">{t("shownOnce")}</p>
      <input readOnly value={link} aria-label={t("link")} onFocus={(e) => e.currentTarget.select()} className="rounded-md border border-border bg-bg px-3 py-2 font-mono text-sm" />
      <button
        type="button"
        onClick={() => void navigator.clipboard.writeText(link).then(() => setCopied(true))}
        className="self-start rounded-md bg-accent px-3 py-1 text-accent-fg"
      >
        {t("copy")}
      </button>
      <span role="status" className="text-sm text-muted">
        {copied ? t("copied") : ""}
      </span>
    </div>
  );
}
