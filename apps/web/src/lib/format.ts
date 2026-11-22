/** A 0-100 score in the locale's percent style: "45,3 %" in Spanish, "45.3%" in English. */
export function percent(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(value / 100);
}
