import contract from "@/lib/api/openapi.json";

/** What the public API reference shows of one key route (public-api-docs spec, issue 334). */
export type Field = { name: string; type: string; required: boolean; limits: string[] };
export type Operation = { id: string; method: string; path: string; scope: string | null; body: Field[] };

type Schema = {
  $ref?: string; type?: string; anyOf?: Schema[]; items?: Schema; enum?: unknown[]; format?: string;
  minLength?: number; maxLength?: number; minimum?: number; maximum?: number; maxItems?: number;
  properties?: Record<string, Schema>; required?: string[];
};
type Op = { operationId: string; tags?: string[]; "x-atesta-scope"?: string; requestBody?: { content: Record<string, { schema: Schema }> } };

const schemas = (contract as unknown as { components: { schemas: Record<string, Schema> } }).components.schemas;
const resolve = (s: Schema): Schema => (s.$ref ? schemas[s.$ref.split("/").pop()!] ?? {} : s);

function typeOf(s: Schema): string {
  const r = resolve(s);
  if (r.anyOf) return r.anyOf.map(typeOf).join(" | ");
  if (r.enum) return r.enum.map((v) => JSON.stringify(v)).join(" | ");
  if (r.type === "array") return `${typeOf(r.items ?? {})}[]`;
  if (s.$ref) return s.$ref.split("/").pop()!;
  return r.format ? `${r.type} (${r.format})` : r.type ?? "object";
}

function limits(s: Schema): string[] {
  const r = s.anyOf?.find((a) => a.type !== "null") ?? s;
  const out: string[] = [];
  if (r.minLength !== undefined || r.maxLength !== undefined) out.push(`${r.minLength ?? 0}–${r.maxLength ?? "∞"}`);
  if (r.minimum !== undefined || r.maximum !== undefined) out.push(`${r.minimum ?? "−∞"}–${r.maximum ?? "∞"}`);
  if (r.maxItems !== undefined) out.push(`≤ ${r.maxItems}`);
  return out;
}

/** Every operation an API key may call (tag api-keys), in contract order, without the rest. */
export function keyOperations(): Operation[] {
  const paths = (contract as unknown as { paths: Record<string, Record<string, Op>> }).paths;
  return Object.entries(paths).flatMap(([path, ops]) => Object.entries(ops)
    .filter(([, op]) => op.tags?.includes("api-keys"))
    .map(([method, op]) => {
      const body = op.requestBody?.content["application/json"]?.schema;
      const shape = body ? resolve(body) : undefined;
      return {
        id: op.operationId, method: method.toUpperCase(), path, scope: op["x-atesta-scope"] ?? null,
        body: Object.entries(shape?.properties ?? {}).map(([name, field]) => ({
          name, type: typeOf(field), required: shape?.required?.includes(name) ?? false, limits: limits(field),
        })),
      };
    }));
}
