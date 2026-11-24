import type { Metadata } from "next";
import { PublicCard } from "@/components/public/public-card";
import { AcceptInvite } from "@/components/accept-invite";

// Belt and braces: CloudFront also sends Referrer-Policy: no-referrer on /invite (web-shell spec).
export const metadata: Metadata = { referrer: "no-referrer" };

export default function InvitePage() {
  return (
    <main id="content" tabIndex={-1} className="public-card-page">
      <PublicCard><AcceptInvite /></PublicCard>
    </main>
  );
}
