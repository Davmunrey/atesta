// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { INVITE_KEY, captureInviteToken, forgetInviteToken } from "@/lib/invite";

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.restoreAllMocks());

it("moves the fragment token to sessionStorage and removes it from the URL", () => {
  window.history.replaceState(null, "", "/invite#token=abc_DEF-123");
  expect(captureInviteToken()).toBe("abc_DEF-123");
  expect(sessionStorage.getItem(INVITE_KEY)).toBe("abc_DEF-123");
  expect(window.location.href).toBe("http://localhost:3000/invite");
});

it("finds the token again after the sign-in round trip", () => {
  sessionStorage.setItem(INVITE_KEY, "kept");
  window.history.replaceState(null, "", "/invite");
  expect(captureInviteToken()).toBe("kept");
});

it("forgets the token", () => {
  sessionStorage.setItem(INVITE_KEY, "kept");
  forgetInviteToken();
  expect(sessionStorage.getItem(INVITE_KEY)).toBeNull();
});

it("survives disabled storage: the URL is still cleaned", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("denied", "SecurityError");
  });
  window.history.replaceState(null, "", "/invite#token=abc");
  expect(captureInviteToken()).toBe("abc");
  expect(window.location.hash).toBe("");
});
