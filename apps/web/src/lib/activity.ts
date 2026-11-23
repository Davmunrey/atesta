/**
 * Audit actions as people read them (ui-polish spec, readable activity). Message keys cannot hold
 * dots, so "requirement.assessed" is stored as "requirement_assessed". An action without a label
 * reads as "Other action"; the code itself is never shown to a person.
 */
type Translate = ((key: string) => string) & { has: (key: string) => boolean };

export function activityLabel(t: Translate, action: string): string {
  const key = `actions.${action.replaceAll(".", "_")}`;
  return t.has(key) ? t(key) : t("unknown");
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** A readable target (framework key, requirement code) or nothing: database ids mean nothing here. */
export function activityTarget(target: string | null | undefined): string | null {
  return target && !UUID.test(target) ? target : null;
}
