import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";
import { generate } from "@atesta/ui/gen-api-types";

const API = join(import.meta.dirname, "../../src/lib/api");

it("schema.d.ts matches a fresh generation from openapi.json", async () => {
  expect(readFileSync(join(API, "schema.d.ts"), "utf8"), "run: pnpm gen:api").toBe(await generate(join(API, "openapi.json")));
});
