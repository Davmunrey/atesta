import type { ReactNode } from "react";

/**
 * A labelled field in a form (DESIGN.md, "Forms"): the label above, the control (a `.field` with
 * this `id`), then a hint or the field's error, which the control names in `aria-describedby`
 * as `${id}-hint`. `wide` spans the form's columns.
 */
export function FormField({ id, label, hint, error, wide, children }: {
  id: string; label: ReactNode; hint?: ReactNode; error?: ReactNode; wide?: boolean; children: ReactNode;
}) {
  return <div className={`form-field${wide ? " form-wide" : ""}`}>
    <label htmlFor={id}>{label}</label>
    {children}
    {error ? <span id={`${id}-hint`} className="form-error">{error}</span> : hint ? <span id={`${id}-hint`} className="form-hint">{hint}</span> : null}
  </div>;
}
