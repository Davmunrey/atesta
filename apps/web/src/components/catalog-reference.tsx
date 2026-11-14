export function CatalogReference({ value }: { value: string }) {
  let safe = false;
  try { const url = new URL(value); safe = ["https:", "http:"].includes(url.protocol) && !url.username && !url.password; } catch { /* A catalog reference may be plain text. */ }
  return safe ? <a href={value} className="text-link underline" target="_blank" rel="noopener noreferrer">{value}</a> : <span>{value}</span>;
}
