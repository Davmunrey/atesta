import codes from "./error-codes.json";

const KNOWN = new Set<string>(codes);

/** The API's error code from a response body (`{"detail": {"code": ...}}`), if it has one. */
export function errorCode(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null) return null;
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

/** Message key for a code; unknown codes get the generic message, never the raw code. */
export function messageKey(code: string | null): string {
  return code !== null && KNOWN.has(code) ? `errors.${code}` : "errors.unknown";
}
