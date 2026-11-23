# Spec: complete internationalization (ES and EN)

- Issue: #146. Builds on `web-shell.md` (locale cookie) and `requirement-register.md` (export).
- Status: built (2026-11-23: every acceptance criterion is implemented and covered by the tests its test plan names)

Every word a person reads in Atesta exists in Spanish and English. The one exception is official
framework text that exists only in Spanish (rule 10): it is never translated from memory. It is
marked as Spanish and labelled as official.

## Acceptance criteria

**Language choice**
- [ ] A first visit without the language cookie follows the browser: English when the first
  supported language in `navigator.languages` is English, Spanish otherwise. An explicit choice
  (the cookie) always wins.

**Messages**
- [ ] **Plurals:** counted messages use ICU plural forms: "1 requisito disponible", "2 requisitos disponibles", "Applies to 1".
- [ ] **Guard test:** a message with a count placeholder and no plural form fails.
- [x] **Stored codes:** a code the API stores and returns in a response field (a scan's
  `error_code`) is in the contract code list, so the web test that every API error code has
  ES and EN text covers it (#270). Tests: `apps/api/tests/test_scan_error_codes.py`,
  `apps/web/tests/unit/errors.test.ts`.
- [ ] **No hardcoded text:** user-facing text in components is never written inline, neither JSX text nor `aria-label`, `title`, `placeholder` or `alt`. A guard test fails on any.

**Formats**
- [ ] **Percentages:** formatted with the locale's percent style ("45,2 %" in Spanish, "45.2%" in English), never by appending " %".
- [ ] **Guard test:** hand-built percentages fail.

**Official Spanish-only text in the English interface**
- [ ] Requirement titles without an English official title, group titles, selection rules and scope axes carry `lang="es"`, so screen readers and translators treat them as Spanish.
- [ ] The framework page says once, in English, that measure titles and official texts are the official Spanish text.

**Statement of applicability export (CSV)**
- [ ] `GET …/applicability.csv?lang=es|en` (Spanish by default) writes headers, decisions, implementation states and the comment lines in that language. The web link passes the interface language.
- [ ] **Official columns:** the measure title column holds the official Spanish title, and its English header says so.
- [ ] **Excel:** the file starts with a UTF-8 byte order mark, so Excel shows accents correctly.
- [ ] **Message files:** API user-facing strings live in `apps/api/src/atesta_api/messages/{es,en}.json`, with a parity test, as the web messages do. The not-a-certification statement comes from these files.

## Out of scope

- More languages (Catalan, Basque, Galician, Portuguese). The structure allows adding them later.
- Translating official framework texts. That needs an official translation as the source.

## Test plan

- **Web unit tests:**
  - browser-language detection and cookie precedence;
  - plural rendering in ES and EN;
  - the plural and hardcoded-text guards;
  - percent formatting in both locales;
  - `lang="es"` on fallback titles and the official-text note.
- **Postgres:**
  - CSV in English and Spanish (headers, values, BOM);
  - an unknown `lang` returns 422;
  - the message files have the same keys.
