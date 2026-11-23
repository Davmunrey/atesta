import { Suspense, type ReactNode } from "react";
import { AuthGate } from "@/components/auth-gate";
import { ConsoleShell } from "@/components/console-shell";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <Suspense>
        <ConsoleShell>{children}</ConsoleShell>
      </Suspense>
    </AuthGate>
  );
}
