"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMe } from "@/components/auth-gate";
import { ErrorMessage } from "@atesta/ui/error-message";
import { ReportView } from "@/components/report-view";
import { ApiError } from "@atesta/ui/api-error";
import { selectOrg } from "@/lib/org";

export default function ReportPage() {
  return <Suspense><Page /></Suspense>;
}

/** The current month in Spain, where the report's month boundaries are drawn. */
function currentMonth(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Madrid", year: "numeric", month: "2-digit" }).format(new Date()).slice(0, 7);
}

function Page() {
  const params = useSearchParams();
  const org = selectOrg(useMe().memberships, params.get("org"));
  if (org === null) return <ErrorMessage error={new ApiError(404, "identity.not_found")} />;
  return <ReportView org={org} initialMonth={params.get("month") ?? currentMonth()} />;
}
