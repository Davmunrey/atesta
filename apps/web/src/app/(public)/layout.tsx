import type { ReactNode } from "react";

export default function PublicLayout({ children }: { children: ReactNode }) {
  return <div className="public-surface min-h-dvh bg-bg text-fg">{children}</div>;
}
