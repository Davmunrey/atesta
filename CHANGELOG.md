# Changelog

Every change merged into `main`, as someone using or auditing Atesta would want it described.
Entries arrive as files in [changes/](changes/README.md) and are folded in here when a release
is cut; nobody edits this file in a feature pull request.

## Unreleased

See [changes/](changes/) for merged changes not yet released. Changes before this changelog
existed are recorded in the merged pull requests up to #110.

## v2026.11.1 (2026-11-23)

### Added

- **Every merged change is recorded in a changelog fragment, checked in CI.** (#110) Fragments in `changes/` are folded into `CHANGELOG.md` at release, so open pull requests never conflict on it.
- **The repository now states the engineering roadmap and its gates.** (#131) `ROADMAP.md` orders Gate A, the parallel preparation packs, Gate B and the device agent, and names what only a human can do.
- **Organizations can record their scope, their own assessment of each requirement and their reviewer's analysis, and export a statement of applicability.** (#133) Atesta proposes applicability from the pack's selection rules; a person always decides. The JSON and CSV export carries an empty signer block and says it is not a certification. Web screens follow.
- **A new organization now sees its first steps, and the framework page leads with its self-assessment.** (#137) Scope, measure-by-measure assessment grouped by family, the security officer's review and the statement-of-applicability export are on screen. Templates without requirements sort last, and internal versions and hashes move out of the way.
- **Agents now design the app with the impeccable and modern-web-guidance skills, vendored text-only at pinned commits; taste-skill is reserved for the landing page.** (#139)
- **Organizations now see their self-assessment progress over time, who owns each measure and what is overdue, and admins see who did what.** (#142) A daily line of implemented measures, open measures by owner, an activity page from the audit log. Every figure comes from recorded rows; devices wait for the on-device agent.
- **Roles for real teams: contributors, an external auditor and Mi trabajo.** (#144) A contributor assesses only the measures assigned to them. An external auditor reads the workspace and exports the statement of applicability until an end date, at most a year ahead, and never writes: the API refuses every auditor write in one place. Mi trabajo lists each person's measures across frameworks, soonest first, with overdue ones flagged.
- **Atesta speaks Spanish and English throughout.** (#146)
  - **Interface:** a first visit follows the browser's language. Counts read naturally ("1 requisito disponible"), and percentages follow each language's format.
  - **Official text:** official Spanish-only text is marked as Spanish and labelled in the English interface.
  - **Export:** the statement of applicability CSV comes in the reader's language, with an Excel-friendly encoding.
  - **Guard tests** keep every new string bilingual.
- **NIS2 arrives, and every pack shows how much of its source it covers.** (#148)
  - **NIS2:** 23 official requirements, in Spanish and English from the Official Journal: governance, the ten minimum risk-management measures and incident reporting, linked to the preparation guides as unreviewed candidates.
  - **Source coverage:** each pack now lists every article, provision and annex of its source, imported or excluded with its reason. ENS has its ledger too.
- **GDPR security of processing, from the official text.** (#150)
  - **Requirements:** 14 requirements from Articles 32 to 34 of the GDPR (security measures, breach notification to the authority within 72 hours and communication to data subjects), in Spanish and English from the Official Journal.
  - **Coverage:** the coverage ledger accounts for all 99 articles.
- **DORA, from the official text.** (#152)
  - **Requirements:** 22 articles on ICT risk management, incidents, resilience testing and third-party risk, in Spanish and English from the Official Journal.
  - **Coverage:** the coverage ledger accounts for all 64 articles.
- **The device agent is designed, not built: read-only, minimal data and transparent to employees.** (#154)
  - **ADR-014, the specification and a threat model** fix the rules: no remote commands, no remediation, a closed list of reported fields, signing and notarization.
  - **An employee notice template** refers to LOPDGDD art. 87.
  - **Build gate:** building it waits for design partners to ask.
- **Owners can take their data and close their organization; Atesta erases it 30 days later.** (#156)
  - **Export:** a JSON file with everything the organization recorded, without credentials.
  - **Closure:** closing needs the organization's exact name and can be cancelled until the erase date, which every member sees.
  - **Erasure:** an operator command deletes every row of the organization, leaving a receipt without names or content (GDPR art. 28(3)(g)).
  - **Runbooks:** onboarding, offboarding and security incidents now have runbooks.
- **The repository states how it is governed, and releases fold the changelog with one command.** (#158)
  - **Governance:** GOVERNANCE.md says who decides what and where it is recorded.
  - **Public repository:** ADR-015 records the controls that keep a public repository safe.
  - **Sub-processors:** a draft sub-processor list for the DPA awaits legal review.
  - **Releases:** `changes release` turns the pending fragments into a CHANGELOG version.
- **The dashboard is now a readiness cockpit.** (#161)
  - **Summary:** a one-line summary of where each framework stands.
  - **Ahora:** a ranked list of what needs attention, linking to where each item is solved.
  - **Framework ledger:** it shows self-assessment progress and the next step. Frameworks in progress come first and empty templates fold away.
  - **Supporting column:** each person's work, the team's open measures and recent activity.
- **The app now works like a cloud console, in Atesta's colours.** (#163)
  - **Top bar:** an ink bar with global search across measures, frameworks and pages, also on Ctrl/⌘K.
  - **Navigation:** a grouped side menu with icons that collapses to a rail, and a drawer on phones.
  - **Pages:** breadcrumbs and a page header on every page, content in panels, and a key-figures strip on the overview.
  - **Marcos:** a new page for frameworks.
- **Access reviews and policies are now recorded in Atesta.** (#165)
  - **Access reviews:** paste the accounts or read a CSV in the browser, decide keep or revoke for each, and close the review. Closing writes an evidence statement on the access review measure.
  - **Policies:** a register with the link to each document, its review period, and append-only approvals with an optional SHA-256 of the file. Each approval writes an evidence statement.
  - **Due evidence:** policies to review or never approved, and overdue access reviews, appear in "Ahora".
- **Training acknowledgements and an incident register with reporting deadlines.** (#166)
  - **Training:** share a secret link to the material; each person confirms with a name and an email, without an account. Closing writes an evidence statement on the awareness measure.
  - **Incidents:** record when you became aware of an incident and whether it is significant or affects personal data. Reporting deadlines come from the framework packs (NIS2 Art. 23(4): 24 h, 72 h, one month after the notification; GDPR Art. 33(1): 72 h). Mark each notice as sent; closing writes an evidence statement on the incident handling measure.
  - **"Ahora"** lists running and missed deadlines, and trainings past their closing date.
- **Your tools can record evidence through an API.** (#169)
  - **Integraciones:** admins create write-only tokens with an expiry, see when each was last used, and revoke them. A token is shown once; Atesta keeps only its fingerprint.
  - **`POST /api/v1/ingest/evidence`:** records an evidence statement on a common control, with safe retries by external id. See `docs/integrations/evidence-api.md`.
- **Scans now feed six more measures.** (#171)
  - **New automated measures:** privileged accounts; user authentication (MFA and methods); sign-in risk and session duration; external sharing in Microsoft 365; email protection; and Google Workspace security alerts.
  - **Checks:** they use 56 more Prowler checks, taken from the pinned engine's own check metadata.
  - **Candidate mappings, pending qualified review:** ENS (op.acc.4, op.acc.5, op.acc.6, mp.s.1, op.mon.1), NIS2 (Art. 21(2)(b), (i) and (j)), GDPR (Art. 32(1)(b)) and DORA (Art. 9 and 10).
- **Implementing Regulation (EU) 2024/2690 is a framework in Atesta.** (#173)
  - **What it holds:** the technical and methodological requirements of NIS2 Article 21(2) for DNS, cloud, data centre, managed and managed security service providers, and the other entities of its Article 1. That is Article 2 and the 161 points of the Annex, in Spanish and English, from the Official Journal.
  - **Every unit is accounted for:** the coverage ledger excludes the significant-incident criteria (Articles 3 to 14) with the reason.
- **The security provisions of the LOPDGDD are a framework in Atesta.** (#175)
  - **Six provisions** of Organic Law 3/2018, from the BOE consolidated text: Articles 5, 28, 31, 32 and 33, and the first additional provision (security measures in the public sector).
  - **Spanish only:** there is no official English text, so none is shown as official.
  - **Every provision is accounted for:** the coverage ledger lists all 144 provisions, with the reason for each one left out.
- **DORA's technical standards on ICT risk management are a framework in Atesta.** (#177)
  - **What it holds:** Delegated Regulation (EU) 2024/1774, Articles 1 to 41, in Spanish and English from the Official Journal, with its 2025 corrigendum applied to Article 22.
  - **Grouping:** by Title and Chapter. Title II is the full framework; Title III is the simplified one, for the entities of Article 16(1) of DORA.
- **Every Prowler check that can run today now feeds a measure.** (#179)
  - Seven new automated measures: Conditional Access coverage, device management, app and integration governance, passwords and recovery, hybrid identity, Google Workspace external collaboration, and directory governance.
  - 99 more checks, so 161 of the 214 pinned checks are used; the remaining 53 need the PowerShell permission, which is not granted yet.
  - Candidate mappings, pending qualified review, in ENS, NIS2, GDPR and DORA.
- **The incident form shows what each framework means by "significant" and "personal data".** (#181)
  - Next to each flag, the official text of the requirement that defines it in each active framework (NIS2 Art. 23(3), GDPR Art. 33(1)), in English where an official English text exists. Atesta shows the text; the decision stays with the organization.
- **The incident form shows when Regulation 2024/2690 considers an incident significant.** (#183)
  - Articles 3 to 14 (general and per type of entity), official text in Spanish and English, next to the "significant" flag. They are not added to the self-assessment, because they are criteria, not measures.
- **An auditor dossier for every framework, with a summary for management.** (#185)
  - One printable document: cover with signature block, management summary (counts, overdue measures, the security officer's latest review, pending routines), statement of applicability, evidence by requirement (scan observation, current review, recorded statements) and the routines of the last 12 months.
  - Print it or save it as PDF from the browser; it says plainly that it is not a certification. Opening it is recorded in the activity log.
- **Ready-made scripts that record evidence on their own.** (#187)
  - In Integraciones, choose what to record (verified backup, approved deployment, vulnerability scan, activity log review) and where it runs (Windows scheduled task, cron, GitHub Actions), and copy the script.
  - The token stays in an environment variable or CI secret, never in the script; a repeated run writes nothing twice.
- **A portfolio view for people who look after several organizations.** (#192)
  - The start page lists every organization you belong to, most urgent first: measures assessed in the frameworks in progress, overdue measures, pending routines and the last assessment, with a portfolio summary on top.
  - Each organization is read with your own access to it; one that fails to load does not hide the others.
- **The incident form shows DORA's major-incident criteria.** (#194)
  - Articles 1 to 9 of Delegated Regulation (EU) 2024/1772 (classification criteria, major incidents and their thresholds), official text in Spanish and English, next to the "significant" flag.
- **A getting-started checklist on the organization overview.** (#196)
  - Seven steps from scope to dossier: scope, first assessments, team, policy, a routine, a connected tool, and the review that leads to the dossier.
  - Each step is marked done from what the organization has actually recorded, and links to where it is done. Admins see it until it is complete or hidden.
- **DORA's reporting deadlines run in the incident register.** (#198)
  - **The three deadlines:** for a major incident, the initial notification (24 hours at the latest from becoming aware), the intermediate report (72 hours after it) and the final report (one month after that). They come from Delegated Regulation (EU) 2025/301.
  - **Not counted yet:** the 4-hour limit from classification. Its deadline title says so.
- **One command builds a realistic demo organization on the local stack.** (#200)
  - `apps/web/scripts/demo-seed.ts`: ENS scope and 40 assessed measures, the security officer review, policies, a closed access review and training, an incident and automatic evidence, all through the public API. See `docs/runbooks/demo.md`.
- **Spec for the hosted environment, ready to deploy without creating anything yet.** (#202)
  - `docs/specs/hosted-environment.md` lists the infrastructure modules, the prod environment, the deploy workflow and the owner's one-day runbook. AWS facts to verify are listed as candidates.
- **A monthly report for management.** (#204)
  - One printable page per month, opened from the side menu:
    - **Done in the month:** assessments, reviews, evidence by people and by tools, policies, access reviews, trainings, incidents and deadlines met.
    - **Current status:** each framework in progress.
    - **What falls due.**
  - It has a signature block, and it says plainly that it is not a certification.
- **Infrastructure base modules, ready and not applied.** (#208)
  - Customer-managed keys with rotation, a private network over two availability zones with flow logs, and a private, encrypted, versioned, TLS-only evidence bucket. They are used by the dev environment and validated in CI; nothing is created in AWS.
- **The hosted database is defined as code: PostgreSQL 16, encrypted, private and TLS-only.** (#214) Backups are kept 14 days in dev and up to 35 in prod. The master password is managed by RDS in Secrets Manager. Statements are never logged. Nothing is applied yet.
- **The containers that will run Atesta in AWS are defined as code, locked down.** (#215) The worker, migrations and one scan task per attempt run on Fargate in private subnets. Secrets come only from Secrets Manager, images are pinned by digest, and per-organization scan roles are capped by a permissions boundary. Nothing is applied yet.
- **The public web and API edge is defined as code.** (#216) The static app is served from a private bucket through CloudFront with the build's CSP, HSTS, nosniff, frame denial and `no-referrer` on invitation and training pages. `/api` and `/auth` go to a load balancer that only accepts CloudFront, over TLS 1.3/1.2, and keeps access logs. Nothing is applied yet.
- **Notification email has a sending identity defined as code, in eu-south-2.** (#217) It signs with DKIM, requires TLS, suppresses bounces and complaints, and lists the DNS records to publish. Nothing is applied yet.
- **Production is defined as code with the same platform as dev.** (#218) Both environments use one composition module and differ only in sizes. Prod has a Multi-AZ database, 35-day backups, a NAT gateway per zone and two API tasks. Cognito email goes through SES in Paris, the single EU exception in ADR-007. Nothing is applied yet.
- **Atesta can be deployed by hand from main with one workflow.** (#219) It builds and pushes the images and the web app, runs migrations with the new image before touching the services, applies the infrastructure, uploads the site and checks the security headers and the API. AWS access is short-lived (OIDC) and every run needs approval in a protected environment. Nothing is deployed until the owner creates the accounts.
- **A deploy runbook takes the owner from no AWS account to a running environment.** (#220) It covers the account steps, first apply, certificates, secrets, a one-off database bootstrap task, the first deploy, rollback and a monthly cost estimate from AWS's eu-south-2 price list: about 138 USD for dev and 228 USD for prod.
- **Each ENS measure lists the evidence CCN-STIC 808 proposes.** (#226) The requirement register and the auditor dossier show a short checklist under every Annex II measure. Atesta wrote it in its own words, in Spanish and English, and each item cites the guide's edition, subsection and page. The list stays a candidate until the owner signs it, and a signature records both the reviewer and the date.
- **Four measures are ready for the Microsoft 365 PowerShell checks.** (#234) Mail threat policies, audit logging, Exchange Online access, and Teams external access and meetings now hold the 53 checks that wait for the PowerShell permission, so all 206 checks the scanner can run, today or once that permission is granted, feed one measure each. They have no result until the permission is granted. Their candidate ENS mappings cite the CCN-STIC 808 and 885A-D guides by section and page; NIS2, GDPR and DORA mirror the existing similar measures. All mappings await qualified review.
- **A scanner note shows where every pinned Prowler check lands.** (#235) It covers each check's control, how Prowler's own compliance mappings compare with Atesta's, and what the PowerShell-backed Microsoft 365 checks need. They issue only reads, but stay excluded until the owner decides on the directory role they require.
- **The API and the worker now have a container image, built and smoke-tested on every pull request.** (#236) Third-party packages install only by hash from the frozen lockfile. The image runs as a non-root user on a read-only root filesystem, and the same image runs database migrations.
- **Every records page opens with a summary for management.** (#240) Policies, access reviews, training, incidents and integrations start with one sentence and their key figures, with what needs action written next to an icon; the register now comes before the form to add a record.
- **Every API route is checked for tenant isolation and the auditor rules.** (#245) A test reads every route from the OpenAPI document: another organization gets 404, an auditor cannot write, expired access is refused, and only a reviewed list of routes answers without a session.
- **The evidence ingestion limits are tested one by one.** (#246) A retired control is refused like an unknown one, each field takes its longest value and refuses one more, and an API token reads nothing.
- **The monthly report is tested line by line, with months cut in Europe/Madrid.** (#247) Every count, the current status per framework and the items that fall due are now checked.
- **SECURITY.md lists what Atesta trusts and the gaps it accepts.** (#260) Each external input names the boundary and the test that hold it, and each accepted gap names the issue that would close it.

### Changed

- **Every issue form asks the author to confirm it carries no customer or personal data.** (#116) The repository is public, so issues are too.
- **CI also runs every Monday and on demand.** (#117) A new advisory or a stale pin now fails on `main` even in a week with no change.
- **Every lint and type suppression in shipped code states its reason, and a test refuses a bare one.** (#121) Seven bare suppressions now say why they are safe.
- **Dependabot no longer bumps procrastinate on its own, because its schema changes need a reviewed queue migration.** (#122) The upgrade to 3.11 is tracked in #123.
- **The job queue runs procrastinate 3.11.0, upgraded through its own release migration.** (#123) The queue's SQL is copied from each release and checked by digest. A later version that changes the queue schema fails CI until a migration applies it.
- **The interface no longer tells a customer it "complies".** (#130) Requirement and check states read Superado / No superado and manual reviews read Implantado / No implantado. The score help says it is not a conformity assessment, and a test refuses compliance claims in every message, the README and PRODUCT.md.
- **The AWS provider moves to 6.73.0 in every OpenTofu directory at once, and Dependabot now groups provider updates.** (#135) Per-directory updates had left the modules and the lock file out of step.
- **The workspace shows only what the task needs: one account button, the organization name instead of a single-item switcher, official BOE headings for each group in the BOE's order, and the not-a-certification note once, in the footer.** (#140)
- **Owner decisions recorded.** (#188)
  - **Accepted:** ADR-012 amendments 3, 4 and 5, ADR-014 (device agent) and ADR-015 (public repository; it is to become private).
  - **Dependabot:** it now proposes procrastinate updates. The queue migration test keeps any schema change from landing unreviewed.
- **The app works on a phone without sideways scrolling.** (#238) Tables turn into labelled rows on narrow screens, chart labels keep their size, controls and standalone links are full-size touch targets, fields no longer make phones zoom, and no text is under 13 px.
- **Activity reads as sentences, and dark mode keeps its structure.** (#239) Every recorded action has a Spanish and English label and no database ids are shown; table headers, hovers and inline forms stay visible in dark mode; requirement states carry an icon beside their label; reports print on white.
- **CloudFront is accepted as the edge for the app and its API, and prod budget alerts move to 250, 350 and 450.** (#286) ADR-007 amendment 2 records the exception to EU-only processing (transit only, nothing cached for the API, TLS end to end, ENS High scope) and the sub-processor list names CloudFront. Dev keeps 150, 250 and 400.

### Removed

- **Removed two web components that nothing used.** (#255) The pre-console app header and organization navigation, and the styles only they used.

### Fixed

- **Five automated measures can pass again.** (#233) They listed eight Prowler checks that the scanner never runs, so they could fail but never pass. Their guides now say which aspects need documentary evidence instead.
- **The API no longer uses SQLAlchemy calls deprecated in 2.1.** (#248) The test suite now fails on any such call, so an upgrade cannot break the API unnoticed.
- **ENS mp.s.2 reads "servicios web deberán", as the BOE prints it.** (#249) The imported text had lost the space after "web".
- **The README quick start runs the checks as CI does.** (#250) It sets the test database and points to the steps that start the API locally.
- **A failed or blocked scan explains why, in Spanish and English.** (#270) The seven scan failure codes now have messages, and a test fails if the API can store a code without them.

### Security

- **`main` is protected by a ruleset, and the public repository reports vulnerabilities privately.** (#112) Every CI job is required and merges are squash-only, with no bypass. Secret scanning with push protection is on, fork pull requests wait for approval, and `SECURITY.md` records each setting and why CodeQL is not used.
- **Every pull request is scanned for secrets by a pinned, checksum-verified gitleaks, and `main` requires the scan.** (#118) Reviewed test fixtures are ignored by exact fingerprint, so a new secret in the same file is still caught.
- **CI fails on any GPL or AGPL Python dependency, and allows LGPL only for the libraries listed in `THIRD_PARTY_NOTICES.md`.** (#119) The web bundle already had this check; the Python side had none.
- **Vendored agent skills are hash-checked against `.claude/skills/VENDORED.sha256`.** (#120) An edit to a reviewed third-party skill now fails the tests until the manifest is regenerated with a review.
- **The web's Content-Security-Policy no longer grows with each page.** (#212) The build moves every inline script into a same-origin file named by its SHA-256, so the policy is `script-src 'self'` with no hashes: 194 of CloudFront's 1,783 characters instead of 1,652.
- **A link that is itself a credential is refused on every path into evidence.** (#256) The ingestion API, policies and training campaigns now refuse, like the web form, a reference link whose query or fragment carries a signature or token, because evidence statements can never be deleted.
- **The API never logs request query strings.** (#257) The API image starts without uvicorn's access log, so the sign-in callback's code and state never reach a log; a test runs the image's own command to hold it.
- **Pinned base images are kept current.** (#259) Dependabot now proposes updates to the digest-pinned images in the Dockerfiles and compose file, after the same 7-day cooldown as every other dependency.
- **Logs no longer carry database row values, OAuth codes or unexpected scanner fields.** (#269) An error in the API or the worker is logged with its type, SQLSTATE and constraint, never its message: PostgreSQL's `DETAIL` line holds the failing row. Access-log lines drop the query string, and the local scanner runner forwards only the wrapper's own fields.
