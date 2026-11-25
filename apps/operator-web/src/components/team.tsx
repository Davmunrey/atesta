"use client";

import { useTranslations } from "next-intl";
import { Fragment, useId, useState } from "react";
import { Badge } from "@atesta/ui/badge";
import { FormField } from "@atesta/ui/form";
import { Empty, LoadError, Loading, Panel } from "@atesta/ui/page-frame";
import { type StaffMember, useChangeStaff, useStaffList } from "@/lib/api/admin";
import type { StaffRole } from "@/lib/roles";
import { ActionForm } from "./action-form";
import { AdminPage } from "./admin-page";
import { useStaff } from "./portal-shell";

const ROLES: StaffRole[] = ["admin", "billing", "support"];

/** Screen 10 of the operator-portal spec: staff, their role and access; never one's own row.
 *  Creating an account in the staff pool is an owner step in the runbook. */
export function Team() {
  const t = useTranslations("team");
  return <AdminPage title={t("title")} description={t("description")}><TeamBody /></AdminPage>;
}

function TeamBody() {
  const t = useTranslations("team");
  const role = useTranslations("portal.role");
  const me = useStaff();
  const list = useStaffList();
  const [open, setOpen] = useState<string | null>(null);
  return <>
    <Panel>{list.isPending ? <Loading />
      : list.isError ? <LoadError error={list.error} onRetry={() => void list.refetch()} />
      : list.data.length === 0 ? <Empty>{t("empty")}</Empty>
      : <div className="table-region" role="region" aria-label={t("list")} tabIndex={0}><table className="w-full text-left">
        <thead><tr><th scope="col">{t("email")}</th><th scope="col">{t("role")}</th><th scope="col">{t("access")}</th><th scope="col">{t("actions")}</th></tr></thead>
        <tbody>{list.data.map((s) => <Fragment key={s.id}>
          <tr><td>{s.email}</td><td data-label={t("role")}>{role(s.role)}</td>
            <td data-label={t("access")}>{s.disabled_at ? <Badge state="staffDisabled">{t("disabled")}</Badge> : <Badge state="staffEnabled">{t("enabled")}</Badge>}</td>
            <td data-label={t("actions")}>{s.email === me.email ? <span className="text-muted">{t("you")}</span>
              : <button type="button" className="dashboard-button" aria-expanded={open === s.id} onClick={() => setOpen(open === s.id ? null : s.id)}>{t("manage")}</button>}</td></tr>
          {open === s.id ? <tr className="row-detail"><td colSpan={4}><Manage member={s} /></td></tr> : null}
        </Fragment>)}</tbody>
      </table></div>}
    </Panel>
  
  </>;
}

function Manage({ member }: { member: StaffMember }) {
  const t = useTranslations("team");
  const role = useTranslations("portal.role");
  const change = useChangeStaff();
  const access = useChangeStaff();
  const id = useId();
  const [next, setNext] = useState<StaffRole>(ROLES.find((r) => r !== member.role)!);
  return <div className="panel-flow">
    <ActionForm label={t("changeRole", { email: member.email })} submit={t("changeRoleAction")} mutation={change}
      onSubmit={(v, done) => change.mutate({ id: member.id, role: next, reason: v.reason }, { onSuccess: done })}>
      <FormField id={id} label={t("newRole")}>
        <select id={id} className="field" value={next} onChange={(e) => setNext(e.target.value as StaffRole)}>
          {ROLES.filter((r) => r !== member.role).map((r) => <option key={r} value={r}>{role(r)}</option>)}</select>
      </FormField>
    </ActionForm>
    {member.disabled_at
      ? <ActionForm label={t("enable", { email: member.email })} submit={t("enableAction")} mutation={access}
        onSubmit={(v, done) => access.mutate({ id: member.id, disabled: false, reason: v.reason }, { onSuccess: done })} />
      : <ActionForm label={t("disable", { email: member.email })} submit={t("disableAction")} danger mutation={access}
        onSubmit={(v, done) => access.mutate({ id: member.id, disabled: true, reason: v.reason }, { onSuccess: done })} />}
  </div>;
}
