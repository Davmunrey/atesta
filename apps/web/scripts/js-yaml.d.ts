/** The part of js-yaml (MIT, pinned in package.json) the build scripts use; it ships no types. */
declare module "js-yaml" {
  export function load(source: string): unknown;
}
