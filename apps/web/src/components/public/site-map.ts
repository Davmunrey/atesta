/**
 * The public site's map (landing-legal amendment A3, issue 371). A page appears in the header and
 * footer only once it exists; each page batch flips its own flag, so no link ever lands on a 404.
 */
export const PAGES = { producto: true, ens: true, seguridad: true, consultoras: true } as const;

export type MenuItem = { key: "assess" | "routines" | "incidents" | "dossier" | "assistant" | "api" | "apiRef" | "mcp"; href: string };

const how = "/#how-title";
export const PRODUCT: { group: "prepare" | "respond" | "integrate"; items: MenuItem[] }[] = [
  { group: "prepare", items: [{ key: "assess", href: PAGES.producto ? "/producto#autoevaluacion" : how }, { key: "routines", href: PAGES.producto ? "/producto#rutinas" : how }] },
  { group: "respond", items: [{ key: "incidents", href: PAGES.producto ? "/producto#incidentes" : how }, { key: "dossier", href: PAGES.producto ? "/producto#dossier" : how }] },
  { group: "integrate", items: [{ key: "assistant", href: PAGES.producto ? "/producto#asistente" : how }, { key: "api", href: PAGES.producto ? "/producto#api" : "/docs/api" }] },
];
export const DOCS: MenuItem[] = [{ key: "apiRef", href: "/docs/api" }, { key: "mcp", href: "/docs/mcp" }];
export const LINKS = [
  ...(PAGES.ens ? [{ key: "ens", href: "/ens" }] : []),
  ...(PAGES.seguridad ? [{ key: "security", href: "/seguridad" }] : []),
  ...(PAGES.consultoras ? [{ key: "consultancies", href: "/consultoras" }] : []),
] as const;
