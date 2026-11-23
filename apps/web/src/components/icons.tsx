/** Atesta's drawn icon set (console-shell spec): 24-unit grid, 1.75 stroke, round joins, currentColor. */
import type { ReactNode, SVGProps } from "react";

const PATHS: Record<string, ReactNode> = {
  home: <><path d="M3.5 10.5 12 4l8.5 6.5" /><path d="M5.5 9v10.5h13V9" /><path d="M10 19.5v-5h4v5" /></>,
  work: <><rect x="4.5" y="4" width="15" height="16.5" rx="1.5" /><path d="m8 9 1.5 1.5L12 8" /><path d="M14 9.5h2.5" /><path d="m8 15 1.5 1.5L12 14" /><path d="M14 15.5h2.5" /></>,
  frameworks: <><path d="m12 4 8.5 4.5L12 13 3.5 8.5Z" /><path d="m3.5 12.5 8.5 4.5 8.5-4.5" /><path d="m3.5 16.5 8.5 4.5 8.5-4.5" /></>,
  members: <><circle cx="9" cy="8.5" r="3.25" /><path d="M3.5 19.5c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5" /><path d="M15.5 5.5a3.25 3.25 0 0 1 0 6.25" /><path d="M17.5 14.6c1.6.6 2.7 2.4 3 4.9" /></>,
  invitations: <><rect x="3.5" y="5.5" width="17" height="13" rx="1.5" /><path d="m4 7 8 6 8-6" /></>,
  activity: <><path d="M3.5 12h4l2.5-6.5 4 13 2.5-6.5h4" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 3.5v2.25M12 18.25v2.25M3.5 12h2.25M18.25 12h2.25M6 6l1.6 1.6M16.4 16.4 18 18M6 18l1.6-1.6M16.4 7.6 18 6" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5.5 5.5" /></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
  reviews: <><path d="M12 3.5 19 6v5.5c0 4.2-2.9 7.7-7 9-4.1-1.3-7-4.8-7-9V6Z" /><path d="m9 12 2.25 2.25L15.5 10" /></>,
  policies: <><path d="M7 3.5h7.5L19 8v12.5H7Z" /><path d="M14.5 3.5V8H19" /><path d="M10 12.5h6M10 16h6" /></>,
  training: <><path d="M3.5 9 12 5l8.5 4-8.5 4Z" /><path d="M7 11v4.5c1.4 1.3 3.1 2 5 2s3.6-.7 5-2V11" /><path d="M20.5 9v5" /></>,
  incidents: <><path d="M12 3.5 20.5 19H3.5Z" /><path d="M12 9.5V14" /><circle cx="12" cy="16.75" r=".5" /></>,
  chevron: <><path d="m9.5 6 6 6-6 6" /></>,
  overdue: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5v5" /><path d="M12 16h.01" /></>,
  missing: <><path d="M12 4 21 19.5H3Z" /><path d="M12 10v4" /><path d="M12 17h.01" /></>,
  pending: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  done: <><circle cx="12" cy="12" r="8.5" /><path d="m8 12.5 2.75 2.75L16 9.5" /></>,
};

export type IconName = keyof typeof PATHS;

/** Decorative by default: the text beside it carries the meaning. */
export function Icon({ name, size = 20, ...rest }: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth={1.75}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" {...rest}>{PATHS[name]}</svg>;
}
