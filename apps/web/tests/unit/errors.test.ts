import { describe, expect, it } from "vitest";
import codes from "@/lib/api/error-codes.json";
import { errorCode, messageKey } from "@atesta/ui/api-error";
import en from "../../messages/en.json";
import es from "../../messages/es.json";

function lookup(messages: object, key: string): unknown {
  return key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], messages);
}

describe("every API error code has a message", () => {
  it("the code list is not empty", () => expect(codes.length).toBeGreaterThan(0));

  it.each(codes)("%s in Spanish and English", (code) => {
    for (const messages of [es, en]) {
      const text = lookup(messages, `errors.${code}`);
      expect(typeof text === "string" && text.length > 0, code).toBe(true);
      expect(messageKey(code, messages)).toBe(`errors.${code}`);
    }
  });

  // The shared ErrorMessage treats a code as known when the messages hold a text for it, so the
  // texts under `errors` are exactly the API's codes plus the generic one: nothing else shows.
  it.each([["es", es], ["en", en]])("%s holds no error text for a code the API does not return", (_, messages) => {
    const leaves = (node: object, prefix = ""): string[] => Object.entries(node).flatMap(([key, value]) =>
      typeof value === "string" ? [`${prefix}${key}`] : leaves(value as object, `${prefix}${key}.`));
    expect(leaves(messages.errors).sort()).toEqual([...codes, "unknown"].sort());
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
    expect(messageKey("identity.last_owner", es)).toBe("errors.identity.last_owner");
  });

  it.each(["identity.something_new", "constructor", "identity", "__proto__", null])("falls back to the generic message for %j", (code) => {
    expect(messageKey(code, es)).toBe("errors.unknown");
  });
});
