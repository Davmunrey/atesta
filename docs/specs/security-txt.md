# Spec: security.txt

- Requirement ids: none (issue 416; owner decisions on 2026-11-24)
- Status: approved for build (the owner chose the contacts and the hosts on 2026-11-24)
- Depends on: web-shell (static export, build chain), infra (the web bucket and CloudFront)

## Problem

SECURITY.md tells a researcher to use GitHub private reporting and promises a `security@`
address and a `/.well-known/security.txt` "when Atesta's domain exists". The domain exists:
the site will be `atesta.cloud` and the app `app.atesta.cloud`. A researcher who finds a problem
on either host looks for that file first, and today gets a 404.

## Decisions (owner, 2026-11-24)

- **Contacts, in this order:** `mailto:security@atesta.cloud`, then GitHub private vulnerability
  reporting ("security@ + GitHub").
- **Hosts:** "estara en atesta.cloud y la app en app.atesta.cloud". Both are canonical.

## Acceptance criteria

Source for every rule: [RFC 9116](https://www.rfc-editor.org/rfc/rfc9116), read on 2026-11-24.

- [ ] `pnpm build` writes `out/.well-known/security.txt` (section 3: the file lives under
      `/.well-known/`).
- [ ] `Contact` (2.5.3, required): the mailbox first, then the GitHub form; each is a `mailto:`
      or `https:` URI.
- [ ] `Expires` (2.5.5, required, exactly once): build time plus 180 days, RFC 3339, UTC. The
      RFC recommends less than a year. It is set by the build, never by hand, so each deploy
      renews it.
- [ ] `Preferred-Languages: es, en` (2.5.8, at most once).
- [ ] `Canonical` (2.5.2), once per host:
      `https://atesta.cloud/.well-known/security.txt` and
      `https://app.atesta.cloud/.well-known/security.txt`.
- [ ] `Policy` (2.5.7): the https link to `SECURITY.md` on `main`.
- [ ] Lines end with LF (section 4 allows LF or CRLF). No field outside this list.
- [ ] The build stops if the generated file breaks one of these rules.
- [ ] The file is served as `text/plain; charset=utf-8` (section 3). `aws s3 sync` sets no
      charset, so the deploy job uploads this one object with that content type, after the sync
      and before the CloudFront invalidation. The deploy smoke check reads the header back.
- [ ] SECURITY.md names both channels and the file, and no longer says they are still to come.
- [ ] The deploy runbook says the `security@atesta.cloud` mailbox must receive mail before the
      first public deploy.

## Out of scope

- Signing the file with OpenPGP (2.3, optional) and an `Encryption` key (2.5.4). Both need a key
  the owner holds (signing keys are an owner decision).
- `Acknowledgments` and `Hiring` (no such page exists).
- Published response targets: SECURITY.md still says they follow.
- A separate distribution for `atesta.cloud`. The same export serves the site and the app; the
  infra stack has one hostname today.

## Test plan

| Test | Proves |
|---|---|
| Unit (`security-txt.test.ts`): contacts and their order, one RFC 3339 `Expires` 180 days ahead, both `Canonical`, languages, policy, LF only, no unknown field | The file's content |
| Unit: `problems()` reports a missing `Contact`, a missing, doubled, malformed, past or year-ahead `Expires`, an `http:` link, a bare email and two language lines | The build guard |
| e2e (`shell.spec.ts`): `GET /.well-known/security.txt` is 200, `text/plain; charset=utf-8`, names the mailbox and has not expired | The built file is served |
| `test_deploy_workflow.py`: the upload step sets the content type on that object after the sync and before the invalidation; the smoke step checks the served header | The deployed content type |
