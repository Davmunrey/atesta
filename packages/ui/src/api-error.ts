/**
 * The API error envelope, shared by every Atesta web app (ADR-017, "API conventions"): an error
 * answers `{"detail": {"code": ...}}`, and the app shows the message it keeps for that code.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
  ) {
    super(code ?? `HTTP ${status}`);
  }
}

/** The API's error code from a response body (`{"detail": {"code": ...}}`), if it has one. */
export function errorCode(body: unknown): string | null {
  if (typeof body !== "object" || body === null) return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail !== "object" || detail === null) return null;
  const code = (detail as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

type Result<T> = { data?: T; error?: unknown; response: Response };

export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (data === undefined) throw new ApiError(response.status, errorCode(error));
  return data;
}

/** For 204 responses, which carry no body. */
export async function expectOk(call: Promise<{ error?: unknown; response: Response }>): Promise<void> {
  const { error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, errorCode(error));
}

/** Message key for a code: `errors.<code>` when the app's messages (next-intl `useMessages()`)
 *  hold a text for it, the generic message otherwise; never the raw code. Each app's messages
 *  hold one text per code its API returns (tested in the app). */
export function messageKey(code: string | null, messages: object): string {
  if (code === null) return "errors.unknown";
  // Own properties only, read as descriptors: "constructor" or "__proto__" never resolve.
  const text = code.split(".").reduce<unknown>((node, part) =>
    typeof node === "object" && node !== null ? Object.getOwnPropertyDescriptor(node, part)?.value : undefined,
  Object.getOwnPropertyDescriptor(messages, "errors")?.value);
  return typeof text === "string" ? `errors.${code}` : "errors.unknown";
}
