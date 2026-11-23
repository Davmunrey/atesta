import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";
import contract from "@/lib/api/openapi.json";
import demo from "../../scripts/demo/es.json";

// The demo seed (docs/runbooks/demo.md) talks to the real API; a required field added to a
// request body must fail here, not in a live demo (#342: scopes became required).
type Schema = { required?: string[]; properties?: Record<string, { enum?: string[]; $ref?: string; items?: { $ref?: string }; minimum?: number; maximum?: number; maxLength?: number }>; enum?: string[] };
const schemas = (contract as unknown as { components: { schemas: Record<string, Schema> } }).components.schemas;

function conforms(body: Record<string, unknown>, name: string) {
  const schema = schemas[name]!;
  expect(Object.keys(body).filter((k) => !(k in (schema.properties ?? {})))).toEqual([]);
  expect((schema.required ?? []).filter((k) => !(k in body))).toEqual([]);
}

it("sends the API token body the contract requires, scopes included", () => {
  conforms(demo.api_token, "TokenIn");
  const scopes = schemas[schemas.TokenIn!.properties!.scopes!.items!.$ref!.split("/").pop()!]!.enum!;
  expect(demo.api_token.scopes.every((s) => scopes.includes(s))).toBe(true);
  expect(demo.api_token.scopes).toEqual(["evidence:write"]); // the seed then ingests evidence with it
  const seed = readFileSync(join(__dirname, "../../scripts/demo-seed.ts"), "utf8");
  expect(seed).toMatch(/call\(api, "POST", `\$\{o\}\/api-tokens`, demo\.api_token\)/);
});

it("sends an ingestion body the contract accepts", () => {
  conforms({ ...demo.evidence, external_id: "demo-2026-11-23" }, "IngestIn");
});
