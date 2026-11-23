import { Suspense, type ReactNode } from "react";
import { AppAssistant } from "@/components/assistant/launcher";
import { AuthGate } from "@/components/auth-gate";
import { ConsoleShell } from "@/components/console-shell";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <Suspense>
        <ConsoleShell>{children}</ConsoleShell>
        <AppAssistant />
      </Suspense>
    </AuthGate>
  );
}
