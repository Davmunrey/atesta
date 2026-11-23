"use client";

import { CookiesLink, LegalDraft } from "@/components/legal-draft";

/** Privacy information (RGPD art. 13.1 and 13.2; LOPDGDD art. 11). Draft. */
export default function Privacy() {
  return <LegalDraft page="privacy" clauses={[
    { id: "controller", fields: ["name", "address", "email"] },
    { id: "dpo" }, { id: "purposes" }, { id: "interests" }, { id: "recipients" }, { id: "transfers" },
    { id: "retention" }, { id: "rights" }, { id: "complaint" }, { id: "required" }, { id: "automated" },
    { id: "cookies", extra: <CookiesLink /> },
  ]} />;
}
