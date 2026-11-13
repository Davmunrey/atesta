import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import { errorCode } from "./errors";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string | null,
  ) {
    super(code ?? `HTTP ${status}`);
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (data === undefined) throw new ApiError(response.status, errorCode(error));
  return data;
}

export const ME = ["me"] as const;

export function useMeQuery() {
  return useQuery({ queryKey: ME, queryFn: () => unwrap(api.GET("/api/v1/me")), retry: false });
}

export function useCreateOrg() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unwrap(api.POST("/api/v1/orgs", { body: { name } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ME }),
  });
}
