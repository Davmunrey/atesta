/**
 * The Atesta mark (DESIGN.md, "Brand system"; landing-legal amendment A1): a double seal ring around
 * three ledger lines, the middle one attested on the highlighter. Decorative beside the live wordmark,
 * so it is hidden from assistive technology. The same geometry lives in public/brand/atesta-mark.svg.
 */
export function BrandMark({ className }: { className?: string }) {
  return <svg className={`brand-seal${className ? ` ${className}` : ""}`} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="2" />
    <circle cx="16" cy="16" r="11.25" fill="none" stroke="currentColor" strokeWidth="1" />
    <rect x="10.5" y="11" width="9" height="2" rx="1" fill="currentColor" />
    <rect className="brand-seal-highlight" x="9" y="14" width="14" height="4" rx="0.75" />
    <rect x="10.5" y="15" width="11" height="2" rx="1" fill="currentColor" />
    <rect x="10.5" y="19" width="6" height="2" rx="1" fill="currentColor" />
  </svg>;
}
