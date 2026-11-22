import type { components } from "@/lib/api/schema";

/** UI hints only: they hide what the role cannot do. The API decides (403 is shown as a message). */
export type Role = components["schemas"]["Role"];

const RANK: Record<Role, number> = { auditor: -1, member: 0, admin: 1, owner: 2 };
export const ROLES: Role[] = ["owner", "admin", "member", "auditor"];

export const canChangeRoles = (caller: Role): boolean => caller === "owner";

export const canRemove = (caller: Role, target: Role): boolean =>
  caller === "owner" || (caller === "admin" && (target === "member" || target === "auditor"));

export const canInvite = (caller: Role): boolean => RANK[caller] >= RANK.admin;

export const invitableRoles = (caller: Role): Role[] =>
  canInvite(caller) ? ROLES.filter((role) => RANK[role] <= RANK[caller]) : [];

export const canReviewControls = (caller: Role): boolean => RANK[caller] >= RANK.admin;

/** Members, Mi trabajo and evidence are for contributors and above; auditors only read. */
export const isContributor = (caller: Role): boolean => RANK[caller] >= RANK.member;

/** Admins assess any measure; a contributor only the measures assigned to them. */
export const canAssess = (caller: Role, ownerId: string | null | undefined, userId: string): boolean =>
  canReviewControls(caller) || (caller === "member" && ownerId === userId);

/** The auditor's access window: from tomorrow to a year ahead (rbac spec). */
export function auditorWindow(today: Date = new Date()): { min: string; max: string } {
  const day = (offset: number) => {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + offset));
    return d.toISOString().slice(0, 10);
  };
  return { min: day(1), max: day(365) };
}
