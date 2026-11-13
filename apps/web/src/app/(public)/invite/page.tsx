import type { Metadata } from "next";
import { AcceptInvite } from "@/components/accept-invite";

// Belt and braces: CloudFront also sends Referrer-Policy: no-referrer on /invite (web-shell spec).
export const metadata: Metadata = { referrer: "no-referrer" };

export default function InvitePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-6 px-6">
      <AcceptInvite />
    </main>
  );
}
