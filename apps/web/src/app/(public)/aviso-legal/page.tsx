"use client";

import { LegalDraft } from "@/components/legal-draft";

/** Aviso legal (LSSI art. 10.1 a, b, e, g; f does not apply while no price is shown). Draft. */
export default function LegalNotice() {
  return <LegalDraft page="notice" clauses={[
    { id: "holder", fields: ["name", "address", "email", "contact"] },
    { id: "registry", fields: ["registry"] },
    { id: "nif", fields: ["nif"] },
    { id: "conduct" },
    { id: "prices" },
  ]} />;
}
