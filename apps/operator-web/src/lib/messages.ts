import contractEn from "../../../operator/contract/messages/en.json";
import contractEs from "../../../operator/contract/messages/es.json";
import en from "../../messages/en.json";
import es from "../../messages/es.json";

/**
 * The portal's texts, Spanish first: its own messages plus the `operator.*` error texts the
 * operator API's contract keeps complete (`apps/operator/contract/messages`), never copied.
 */
export const MESSAGES = {
  es: { ...es, errors: { ...es.errors, ...contractEs.errors } },
  en: { ...en, errors: { ...en.errors, ...contractEn.errors } },
} as const;
