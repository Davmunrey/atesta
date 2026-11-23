import { ApiReference } from "@/components/api-reference";
import { keyOperations } from "@/lib/api-reference";

// A server component: the contract is reduced at build time, so the page ships only key routes.
export default function ApiReferencePage() {
  return <ApiReference operations={keyOperations()} />;
}
