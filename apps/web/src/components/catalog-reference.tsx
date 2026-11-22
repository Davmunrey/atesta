/** A short, readable name for a catalog URL: host, document id or last path segment, and section. */
export function referenceLabel(url: URL): string {
  const host = url.hostname.replace(/^www\./, "");
  const segment = url.pathname.split("/").filter(Boolean).at(-1) ?? "";
  const id = url.searchParams.get("id") ?? decodeURIComponent(segment).replace(/\.[a-z]{2,5}$/i, "");
  const short = id.length > 48 ? `${id.slice(0, 45)}…` : id;
  return [host, short, url.hash ? url.hash.slice(1) : ""].filter(Boolean).join(" · ");
}

export function CatalogReference({ value }: { value: string }) {
  let url: URL | null = null;
  try { const parsed = new URL(value); if (["https:", "http:"].includes(parsed.protocol) && !parsed.username && !parsed.password) url = parsed; } catch { /* A catalog reference may be plain text. */ }
  // The full address stays in the title and in the href; the visible text is readable.
  return url ? <a href={value} title={value} className="text-link underline" target="_blank" rel="noopener noreferrer">{referenceLabel(url)}</a> : <span>{value}</span>;
}
