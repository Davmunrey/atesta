import createClient from "openapi-fetch";
import type { paths } from "./schema";

/**
 * Same origin as the page: the HttpOnly session cookie goes with each request, and no token is
 * ever visible to JavaScript (web-shell spec, BFF). Paths are typed from the API's OpenAPI.
 */
export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? "",
  credentials: "same-origin",
  fetch: (request) => globalThis.fetch(request), // looked up per call, not captured at import
});
