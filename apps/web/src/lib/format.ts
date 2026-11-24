/** A 0-100 score in the locale's percent style: "45,3 %" in Spanish, "45.3%" in English. */
export function percent(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(value / 100);
}

/** A file size in the locale's units: "338 kB", "25 MB". Decimal units, as file managers show. */
export function fileSize(locale: string, bytes: number): string {
  const [unit, value] = bytes < 1_000_000 ? (["kilobyte", bytes / 1024] as const) : (["megabyte", bytes / (1024 * 1024)] as const);
  return new Intl.NumberFormat(locale, { style: "unit", unit, unitDisplay: "short", maximumFractionDigits: unit === "megabyte" && value < 10 ? 1 : 0 }).format(value);
}
