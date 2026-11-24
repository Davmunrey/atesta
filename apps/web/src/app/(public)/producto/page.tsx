import { ProductoPage } from "@/components/public/producto-page";
import { loadLandingCatalog } from "@/lib/catalog/landing";

/** /producto is rendered at build time: its measure sheet reads the catalog pack, like the landing. */
export default function Producto() {
  return <ProductoPage measure={loadLandingCatalog().measure} />;
}
