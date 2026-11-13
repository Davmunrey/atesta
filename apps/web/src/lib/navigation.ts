/** Full-page navigation (sign-in, sign-out, after create); one seam for tests. */
export function goTo(url: string): void {
  window.location.assign(url);
}
