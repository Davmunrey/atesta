import { useQuery } from "@tanstack/react-query";
import { unwrap } from "@atesta/ui/api-error";
import { api } from "./client";

export const ME = ["me"] as const;

/** The staff member: email and role (`GET /me`); 401 means signed out, 403 no access. */
export function useMeQuery() {
  return useQuery({ queryKey: ME, queryFn: () => unwrap(api.GET("/api/v1/me")), retry: false });
}
