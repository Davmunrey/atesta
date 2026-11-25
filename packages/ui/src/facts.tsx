import type { ReactNode } from "react";

/** Recorded fields as label and value rows, ruled, one column when the panel is narrow
 *  (DESIGN.md, "Facts"): the owner's billing details in the console, metadata in the portal. */
export function Facts({ children }: { children: ReactNode }) {
  return <dl className="facts">{children}</dl>;
}

export function Fact({ label, children }: { label: ReactNode; children: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}
