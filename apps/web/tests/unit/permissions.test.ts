import { describe, expect, it } from "vitest";
import { loginUrl } from "@/lib/auth";
import { selectOrg } from "@/lib/org";
import { auditorWindow, canAssess, canChangeRoles, canInvite, canRemove, invitableRoles, isContributor } from "@/lib/permissions";

describe("permissions mirror the API (identity-auth spec); the API stays the authority", () => {
  it("only owners change roles", () => {
    expect([canChangeRoles("owner"), canChangeRoles("admin"), canChangeRoles("member")]).toEqual([true, false, false]);
  });

  it.each([
    ["owner", "owner", true], ["owner", "admin", true], ["owner", "member", true],
    ["admin", "owner", false], ["admin", "admin", false], ["admin", "member", true],
    ["admin", "auditor", true], ["member", "member", false], ["auditor", "member", false],
  ] as const)("%s removing %s: %s", (caller, target, allowed) => {
    expect(canRemove(caller, target)).toBe(allowed);
  });

  it("admins and owners invite, up to their own role", () => {
    expect(canInvite("member")).toBe(false);
    expect(invitableRoles("admin")).toEqual(["admin", "member", "auditor"]);
    expect(invitableRoles("owner")).toEqual(["owner", "admin", "member", "auditor"]);
    expect(invitableRoles("member")).toEqual([]);
    expect(invitableRoles("auditor")).toEqual([]);
  });
});

describe("roles and access (rbac spec)", () => {
  it("auditors are not contributors", () => {
    expect((["owner", "admin", "member", "auditor"] as const).map(isContributor)).toEqual([true, true, true, false]);
  });

  it.each([
    ["admin", "someone-else", true], ["owner", null, true],
    ["member", "me", true], ["member", "someone-else", false], ["member", null, false],
    ["auditor", "me", false],
  ] as const)("%s assessing a measure owned by %s: %s", (role, owner, allowed) => {
    expect(canAssess(role, owner, "me")).toBe(allowed);
  });

  it("the auditor end date runs from tomorrow to a year ahead", () => {
    expect(auditorWindow(new Date("2026-11-22T23:30:00Z"))).toEqual({ min: "2026-11-23", max: "2027-11-22" });
  });
});

describe("loginUrl", () => {
  it("carries the language and a same-site return path", () => {
    expect(loginUrl("en", "/app/org?org=1")).toBe("/auth/login?lang=en&return_to=%2Fapp%2Forg%3Forg%3D1");
  });

  it.each(["//evil.example/app", "https://evil.example/", "/\\evil.example", "app"])("drops %s", (target) => {
    expect(loginUrl("es", target)).toBe("/auth/login?lang=es");
  });
});

describe("selectOrg", () => {
  const a = { organization_id: "a", organization_name: "A", role: "owner" as const };
  const b = { organization_id: "b", organization_name: "B", role: "member" as const };

  it("picks the requested membership", () => expect(selectOrg([a, b], "b")).toBe(b));
  it("never picks an org the user is not a member of", () => expect(selectOrg([a, b], "zz")).toBeNull());
  it("is null without a request", () => expect(selectOrg([a, b], null)).toBeNull());
});
