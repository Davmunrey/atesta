import type { components } from "@/lib/api/schema";

/** UI hints only: they hide what the role cannot do. The API decides (403 is shown as a message). */
export type Role = components["schemas"]["Role"];

const RANK: Record<Role, number> = { member: 0, admin: 1, owner: 2 };
export const ROLES: Role[] = ["owner", "admin", "member"];

export const canChangeRoles = (caller: Role): boolean => caller === "owner";

export const canRemove = (caller: Role, target: Role): boolean =>
  caller === "owner" || (caller === "admin" && target === "member");

export const canInvite = (caller: Role): boolean => RANK[caller] >= RANK.admin;

export const invitableRoles = (caller: Role): Role[] =>
  canInvite(caller) ? ROLES.filter((role) => RANK[role] <= RANK[caller]) : [];

export const canReviewControls = (caller: Role): boolean => RANK[caller] >= RANK.admin;
