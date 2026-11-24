import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { components } from "./schema";
import { api } from "./client";
import { ApiError, unwrap } from "./hooks";
import { errorCode } from "./errors";

export const EVIDENCE_PAGE_SIZE = 20;
const path = "/api/v1/orgs/{org_id}/controls/{control_key}/evidence";

export function useControlEvidence(orgId: string, controlKey: string, offset: number, enabled = true) {
  return useQuery({
    queryKey: ["evidence", orgId, controlKey, offset], retry: false, enabled,
    queryFn: () => unwrap(api.GET(path, { params: {
      path: { org_id: orgId, control_key: controlKey }, query: { offset, limit: EVIDENCE_PAGE_SIZE },
    } })),
  });
}

export function useRecordEvidence(orgId: string, controlKey: string) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: (body: components["schemas"]["StatementIn"]) => unwrap(api.POST(path, {
      params: { path: { org_id: orgId, control_key: controlKey } }, body,
    })),
    onSuccess: () => Promise.all([
      client.invalidateQueries({ queryKey: ["evidence", orgId, controlKey] }),
      client.invalidateQueries({ queryKey: ["overview", orgId] }),
    ]),
  });
}

type FileUpload = { submissionId: string; title: string; file: File };

/** Multipart to the API on this origin: the browser never writes to the store (evidence-file-uploads spec). */
export function useUploadEvidenceFile(orgId: string, controlKey: string) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: ({ submissionId, title, file }: FileUpload) => unwrap(api.POST(`${path}/files`, {
      params: { path: { org_id: orgId, control_key: controlKey } },
      body: { submission_id: submissionId, title, file: file as unknown as string },
      bodySerializer: () => {
        const form = new FormData();
        form.set("submission_id", submissionId);
        form.set("title", title);
        form.set("file", file, file.name);
        return form;
      },
    })),
    onSuccess: () => Promise.all([
      client.invalidateQueries({ queryKey: ["evidence", orgId, controlKey] }),
      client.invalidateQueries({ queryKey: ["overview", orgId] }),
    ]),
  });
}

/** The verified bytes, or the API's refusal: an integrity failure is an error, never an empty file. */
export function useDownloadEvidenceFile(orgId: string) {
  return useMutation({
    retry: false,
    mutationFn: async (evidenceId: string) => {
      const { data, error, response } = await api.GET("/api/v1/orgs/{org_id}/evidence/{evidence_id}/file", {
        params: { path: { org_id: orgId, evidence_id: evidenceId } }, parseAs: "blob",
      });
      if (!response.ok || data === undefined) throw new ApiError(response.status, errorCode(error));
      return data as Blob;
    },
  });
}
