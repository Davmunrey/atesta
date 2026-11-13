import { describe, expect, it } from "vitest";
import codes from "@/lib/api/error-codes.json";
import { errorCode, messageKey } from "@/lib/api/errors";
import en from "../../messages/en.json";
import es from "../../messages/es.json";

function lookup(messages: object, key: string): unknown {
  return key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], messages);
}

describe("every API error code has a message", () => {
  it("the code list is not empty", () => expect(codes.length).toBeGreaterThan(0));

  it.each(codes)("%s in Spanish and English", (code) => {
    for (const messages of [es, en]) {
      const text = lookup(messages, messageKey(code));
      expect(typeof text === "string" && text.length > 0, code).toBe(true);
    }
  });
});

describe("errorCode", () => {
  it("reads detail.code", () => {
    expect(errorCode({ detail: { code: "identity.last_owner" } })).toBe("identity.last_owner");
  });

  it.each([null, "x", { detail: [{ msg: "field required" }] }, { detail: { code: 5 } }, {}])(
    "is null for %j",
    (body) => expect(errorCode(body)).toBeNull(),
  );
});

describe("messageKey", () => {
  it("maps a known code to its message", () => {
    expect(messageKey("identity.last_owner")).toBe("errors.identity.last_owner");
  });

  it.each(["identity.something_new", "constructor", null])("falls back to the generic message for %j", (code) => {
    expect(messageKey(code)).toBe("errors.unknown");
  });
});
