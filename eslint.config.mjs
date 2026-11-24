// ESLint finds the nearest config to each file. The shared UI package (packages/ui) has no
// toolchain of its own, so it is linted with the console's rules (ADR-017).
export { default } from "./apps/web/eslint.config.mjs";
