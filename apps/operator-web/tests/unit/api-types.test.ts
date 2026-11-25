import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";
import { generate } from "@atesta/ui/gen-api-types";

// The typed client comes from the operator API's contract, with the console's script (ADR-017).
const SCHEMA = join(import.meta.dirname, "../../src/lib/api/schema.d.ts");
const OPENAPI = join(import.meta.dirname, "../../../operator/contract/openapi.json");

it("schema.d.ts matches a fresh generation from the operator API's openapi.json", async () => {
  expect(readFileSync(SCHEMA, "utf8"), "run: pnpm gen:api").toBe(await generate(OPENAPI));
});
