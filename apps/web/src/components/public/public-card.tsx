import type { ReactNode } from "react";
import { BrandMark } from "@/components/brand-mark";

/** A single-message public page's card (A3, issue 384): centred, with the seal and the highlighter tab. */
export function PublicCard({ children }: { children: ReactNode }) {
  return <div className="public-card"><BrandMark className="public-card-seal" />{children}</div>;
}
