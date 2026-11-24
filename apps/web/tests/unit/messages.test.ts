import { expect, it } from "vitest";
import en from "../../messages/en.json";
import es from "../../messages/es.json";

function leaves(tree: object, prefix = ""): Map<string, unknown> {
  const out = new Map<string, unknown>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object") {
      for (const [k, v] of leaves(value as object, path)) out.set(k, v);
    } else {
      out.set(path, value);
    }
  }
  return out;
}

it("Spanish and English have the same keys", () => {
  expect([...leaves(en).keys()].sort()).toEqual([...leaves(es).keys()].sort());
});

it("every message is a non-empty string", () => {
  for (const [key, value] of [...leaves(es), ...leaves(en)]) {
    expect(typeof value === "string" && value.trim() !== "", key).toBe(true);
  }
});

it("names recurring records one way: never \"rutinas\" or \"routines\" in user-facing text", () => {
  for (const [key, value] of leaves(es)) expect(String(value), key).not.toMatch(/rutina/i);
  for (const [key, value] of leaves(en)) expect(String(value), key).not.toMatch(/routine/i);
});
