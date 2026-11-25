import createClient from "openapi-fetch";
import type { paths } from "./schema";

/**
 * Same origin as the page: the HttpOnly staff session cookie goes with each request, and no token
 * is ever visible to JavaScript (ADR-017, staff session). Paths are typed from the operator API's
 * OpenAPI document (`apps/operator/contract/openapi.json`).
 */
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  credentials: "same-origin",
  fetch: (request) => globalThis.fetch(request), // looked up per call, not captured at import
});
