import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { SCHEMA, generate } from "../../scripts/gen-api-types";

it("schema.d.ts matches a fresh generation from openapi.json", async () => {
  expect(readFileSync(SCHEMA, "utf8"), "run: pnpm gen:api").toBe(await generate());
});
