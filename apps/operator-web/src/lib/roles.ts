import type { components } from "./api/schema";

/** Staff roles (operator-portal spec, permissions matrix); the API enforces them, the UI follows. */
export type StaffRole = components["schemas"]["StaffRole"];
export type Staff = components["schemas"]["MeOut"];

export const isAdmin = (role: StaffRole) => role === "admin";
/** Set plan and add-ons, read and edit billing details. */
export const canBill = (role: StaffRole) => role === "admin" || role === "billing";
