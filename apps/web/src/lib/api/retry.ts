import { ApiError } from "./hooks";

/**
 * Query retry policy (ui-polish spec): a 4xx answer will not change on retry, so it shows at
 * once; a server or network failure is retried once, so an error shows within a few seconds.
 */
export function retryQuery(failures: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failures < 1;
}
