import { EnsPage } from "@/components/public/ens-page";
import { loadEnsCatalog } from "@/lib/catalog/ens";

/** /ens is rendered at build time: the measures come from the catalog pack, not from the client. */
export default function Ens() {
  return <EnsPage catalog={loadEnsCatalog()} />;
}
