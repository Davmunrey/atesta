import { LandingPage } from "@/components/landing/landing-page";
import { loadLandingCatalog } from "@/lib/catalog/landing";

/** The landing is rendered at build time: its measure and mappings come from the catalog pack. */
export default function Landing() {
  return <LandingPage catalog={loadLandingCatalog()} />;
}
