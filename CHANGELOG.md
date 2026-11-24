# Changelog

Every change merged into `main`, as someone using or auditing Atesta would want it described.
Entries arrive as files in [changes/](changes/README.md) and are folded in here when a release
is cut; nobody edits this file in a feature pull request.

## Unreleased

See [changes/](changes/) for merged changes not yet released. Changes before this changelog
existed are recorded in the merged pull requests up to #110.

## v2026.11.2 (2026-11-24)

### Added

- **Incidents record when they were classified as significant, so DORA's 4-hour clock runs.** (#224) The initial notification under Delegated Regulation (EU) 2025/301 is now due 4 hours after classification as major, and no later than 24 hours from awareness; a classification after those 24 hours runs 4 hours from classification (Art. 5(2)). The time is given with the incident or recorded later. Incidents without it keep the 24-hour limit.
- **The ENS scope step guides the valuation dimension by dimension.** (#225) Following CCN-STIC 803, the worksheet asks about each information type (confidentiality, integrity, traceability, authenticity) and then each service (availability), cites the guide's section and page, and fills the scope with the highest level per dimension and the category it leads to. The worksheet is not stored; the guide's own text is not copied.
- **The ENS scope can adopt the CCN-STIC 890C essential-requirements profile.** (#227) Smaller entities choose the IT or the IT/OT/IoT profile in the scope step, and the register proposes each of the 73 measures from the profile's statement of applicability, citing the guide's section and page. The profile is pack content over the same measures, a candidate until reviewed; every decision stays the organization's.
- **A manual review that marks a control implemented now cites the evidence it rests on.** (#262) A pass needs at least one evidence item linked to that control in the same organization; a fail may cite none. The register, the review history and the auditor dossier list what each review cites, and reviews recorded before this read as citing none.
- **"Scan now" is limited to 6 manual scans per connection per day (Madrid time).** (#265) Each scan reads the customer's whole tenant, which Microsoft and Google throttle; the 7th request gets 429 `scanning.daily_limit` with the time of the next allowed scan. Scheduled and activation scans are never counted.
- **The test suite also runs on the newest CPython (3.15) every Monday and on demand.** (#266) It is its own workflow, never runs on a pull request and is not a required check, so a break shows up early without costing minutes or blocking a merge.
- **Plans are enforced: a request beyond the organization's plan gets 403 `billing.plan_limit`, with its message in Spanish and English.** (#285) Connectors count against the plan's limit, the auditor dossier needs evidence export, and a framework opens only if the plan grants it. Organizations without a plan, every pilot included, keep the business plan and everything they use.
- **The overview shows the records at a glance.** (#287) A "Registros" table lists policies, access reviews, training and incidents, each with its state as icon and text and the sentence its page leads with, so management sees what needs action without opening four pages.
- **taste-skill is vendored for the landing page.** (#307) Text only, at a pinned commit, without its Stop hook, per ADR-013.
- **The landing leads with the ENS.** (#308) A headline for SMEs that sell to the public sector, the product's overview as the hero, the other frameworks as "también cubre", a line for consultancies and a closing request for access. The copy stays within 60 words, the view is illustrative until a recorded run replaces it, and `check-legal` blocks a release while the contact address is a placeholder.
- **The first 19 mappings are signed by the owner.** (#309) Nine ENS mappings whose CCN-STIC citations were checked in the guides, and ten NIS2, GDPR and DORA mappings of the same controls, now carry "David Muñoz" and the review date; every other mapping stays a candidate.
- **The landing shows what the console ships.** (#313) Three product moments follow the hero: a measure's official text and self-assessment, the records an auditor asks for, and a dossier ready to sign. Scans and the assistant join when they ship.
- **A Microsoft 365 connection can now be signed in and consented: the admin's Entra tenant is bound before admin consent is accepted.** (#314) Sign-in and consent travel in a sealed, single-use cookie; a forged tenant, a denied consent or another user's sign-in is refused with its own message, and nothing logs a code or a token. Onboarding stays unavailable until the owner registers the two Microsoft apps.
- **Draft legal notice and privacy pages.** (#316) `/aviso-legal` and `/privacidad` follow LSSI art. 10 and RGPD art. 13 item by item. Each clause is marked as a draft pending legal review, the owner's identity shows as PENDIENTE placeholders, and `check-legal` blocks a release until they are complete and reviewed.
- **Atesta has a brand.** (#323) An original seal mark (a double ring around three ledger lines, one highlighted) with the live wordmark, the highlighter stroke as the one signature motif, and a fuller landing: the problem, how it works in four steps (connecting your systems marked as coming soon), the product views labelled as sample data, the frameworks it covers and a line for consultancies. The owner accepted the spec amendment that raises the copy budget to 200 words.
- **A consented Microsoft 365 connection can now be verified and activated.** (#331) "Verify" runs the connection's first scan, which checks the read-only permissions and that the person who consented is a Global or Privileged Role Administrator of that tenant; only then does the connection become active and start its daily scans.
- **API keys carry explicit scopes, a rate limit per key and a usage log that admins can see.** (#332) An admin picks each permission when creating a key, with none ticked by default: reading compliance or incidents, recording evidence, proposing self-assessments, or recording routines. A read-only key cannot write, and existing keys keep exactly `evidence:write`. Over its limit, a key gets 429 with `Retry-After` and a message in Spanish or English. The usage log records each accepted call's route and scope, never its content.
- **AI agents can work with Atesta through an MCP server, local or hosted, using a scoped API key.** (#333) The tools read frameworks, measures with their official text and citation, gaps, due items and incidents. They record evidence, propose self-assessments for a person to confirm, record incidents and start training campaigns and access reviews. Each tool is one API call, so scopes, rate limits, the usage log, tenancy and audit apply unchanged. Results frame the organization's data with per-response nonces, so text that people wrote is never read as instructions. The local server runs over stdio. The hosted one (Streamable HTTP at `/mcp`) stays off until `ATESTA_MCP_REMOTE=1`.
- **Public pages explain the API and how to connect an AI agent over MCP.** (#334) `/docs/api` lists every route an API key may call, grouped by permission, with its request fields and the errors specific to keys. It is built from the OpenAPI contract, so it cannot drift from the API. `/docs/mcp` explains what an agent can and cannot do, how to connect one on your own computer, and that the hosted server is not available yet. Both pages are in Spanish and English, and Integraciones links to them.
- **ADR-016 sets out an MCP server so AI agents can work with Atesta through scoped API keys; the owner accepted it with ADR-012 amendment 6 on 2026-11-23.** (#338) Specs `api-keys-v2` and `mcp-server` set the scopes, rate limits, usage log, self-assessment proposals that a person confirms, and the framing of customer content returned to agents. ADR-012 amendment 6 lets keys read their own organization's data.
- **An AI agent can propose a self-assessment, and only a person's confirmation records it.** (#339) A key with `assessment:propose` stores a pending proposal for a measure, with its reason. It changes neither the measure nor any count (ADR-005). On the self-assessment page, a person who may assess the measure sees the proposal and the key that sent it, and confirms or rejects it. A confirmation records the assessment in that person's name. Both decisions are audited.
- **API keys can read the compliance state and incidents of their own organization.** (#341) With `compliance:read`, a key reads frameworks with readiness counts, measures with their latest assessment, a measure's official text with its citation (source, section, source SHA-256, catalog version), gaps and due items. With `incidents:read`, it reads open incidents and their reporting clocks. The plan decides frameworks as in the app, and no route can name another organization.
- **Agents gain vendored skills for planning, reviews and messages.** (#350) Six obra/superpowers skills (brainstorming, writing-plans, executing-plans, requesting and receiving code review, finishing a branch), ayghri/i-have-adhd for messages to the owner and juliusbrussee/caveman for agent status messages, text only at pinned commits; AGENTS.md says when each applies and that its own rules win.
- **The landing tells its story as you scroll.** (#356) "Cómo funciona" pins a product frame that changes with each step, "Un año de ENS" walks through a year of sample data, headlines reveal on scroll, the hero figures count up, and the frameworks it covers glide by with a pause button. Phones and reduced motion get a calm, static page.
- **An assistant on the landing and in the app answers from the catalog, with no AI model.** (#357) It quotes official texts and the signed CCN-STIC 808, 890C and 803 content word for word, each with its source, and says so plainly when it has no answer. Five guided questions cover the ENS category, a measure's evidence, the essential profile, incident deadlines and what Atesta covers. In the app, an answer links to that measure in your organization.
- **The assistant's engine searches the catalog and cites every answer, with no AI model.** (#359) A build step indexes official texts, the signed CCN-STIC 808, 890C and 803 content and a product FAQ pending the owner's review. The index is 63 KB gzipped, against a 250 KB budget. Search runs in the browser, so a query never leaves it.
- **Owner runbook for the Microsoft 365 test tenant and the two app registrations.** (#362) Step by step, checked against Microsoft Learn: a paid Business Premium tenant plays the customer, a separate Atesta dev tenant holds the apps, and the scanner's permissions come from the generated allowlist block.
- **The public site shares one header and footer.** (#371) Menus for the product and the docs, a full footer with honest facts (73 medidas con el texto oficial del BOE, evidencias revisadas por el equipo de Atesta, diseñado para alojarse en España, solo lectura, ninguna IA decide), smooth page-to-page transitions, and a customer-logo section that stays empty until a customer gives written permission.
- **The landing shows the product, not a promise.** (#373) The hero opens a real tablist with five sample views (summary, self-assessment, routines, an incident with its NIS2 deadline, the dossier), a proof strip of facts true today, Microsoft 365 and Google Workspace named as "Próximamente", a fifth "incidents" stage in the scroll story, and a ring diagram showing how one common control serves ENS, NIS2, RGPD, LOPDGDD and DORA, with a text equivalent.

### Changed

- **The scanner runs Prowler 5.52.0 instead of 5.49.0.** (#243) The Microsoft 365 and Google Workspace check lists are unchanged (149 and 65 checks). Two Defender outbound anti-spam checks no longer fail when Standard or Strict preset policies exist, and the Google provider now refuses a service-account key whose token endpoint is not Google's. The live goldens against the test tenants run before any customer scan uses the new engine.
- **Pull requests must be up to date with main before they merge.** (#261) Owner decision: no required approvals; the coordinator reviews and merges with CI green.
- **ADR-010 amendment 1 is accepted: customer content reaching the AI is framed by per-request nonce delimiters, and the citation check stays the hard gate.** (#264) Filtering prompt injection is defence in depth only; the framing, the citation check and the relevance threshold are code-owned.
- **The incident form fits a phone.** (#276) Official criteria under each flag are grouped into one disclosure per framework ("Qué dice DORA (9 criterios)"), so the form no longer runs to twenty-odd disclosures. On touch screens, checkboxes and radios are 24 px boxes.
- **Nine specs that are shipped and tested now say so: their status is `built`.** (#282) Auditor dossier, claims honesty, consultancy portfolio, complete i18n, manual control review, organization closure, RBAC, recorded routines and the requirement register.
- **Loading, error and empty states look and behave the same on every page.** (#283) Every page keeps its header while it loads or fails, every failed load offers "Reintentar", and a failing page shows its error within a few seconds: answers that cannot change (4xx) are not retried, and server or network failures are retried once.
- **Expected evidence reads more cleanly.** (#295) A guide reference shared by every item is shown once, the register's disclosure matches its sibling sections, and the dossier keeps the lists closed on screen and opens them only while printing.
- **Dependabot proposes only patch updates for the pinned Python minor and PostgreSQL major (now 3.13 and 18, after #298 and #299).** (#296) Moving to another Python minor or PostgreSQL major is a planned upgrade of every image, CI job and the database together.
- **Atesta runs on Python 3.13 everywhere.** (#298) The API, worker and scanner images share one `python:3.13.18-slim-trixie` base pinned by digest. CI, the type checker, the linter and the scanner's hash-locked requirements move with them. 3.13 is the newest Python that Prowler allows. Only 3.13.x patches arrive through Dependabot.
- **The database moves to PostgreSQL 18, the newest major Amazon RDS offers in eu-south-2.** (#299) The hosted database (RDS, parameter group `postgres18`), CI and local runs now use the same major, with 18.6 pinned by digest; a test keeps them equal. Connection logging keeps the same events under PostgreSQL 18's new `log_connections` list. Nothing was deployed on 16, so no data moves.
- **Public pages share one frame.** (#301) The landing, cookies, invitation, training and 404 pages share the wordmark header, language switcher and footer. Invalid or missing invitation and training links get a heading and a plain next step, and a malformed training link no longer reads as a form error. A new e2e spec holds the public pages to the console's accessibility and layout bar.
- **The console carries the brand.** (#330) The top bar shows the seal lockup, every page title carries the highlighter tab, and the overview marks its one key figure, so the app and the site read as one product.
- **The ENS guide content is signed by the owner.** (#336) The evidence CCN-STIC 808 expects for all 73 measures, both CCN-STIC 890C essential profiles and the CCN-STIC 803 scope helper now show "revisada por David Muñoz" instead of the candidate note.
- **Small fixes from the review of evidence-backed reviews and incident classification.** (#345) The review form's radios and checkboxes share one size (24 px on touch), evidence options read at regular weight, the saved review shows a notice, the classification time input names its help and cannot go before the incident was known, and incident forms no longer print.
- **Small fixes from the reviews of API keys, the docs and the assistant.** (#374) The docs tables have padded cells and rules, the read-only key badge and the scope groups read clearly, scope checkboxes share one size, usage disclosures show a chevron, and the assistant launcher shows the seal, keeps its space inside the footer and no longer prints.

### Fixed

- **The printed dossier lists the evidence each manual review cites.** (#321) The review form also validates a pass without evidence in the same pass as the other fields, shows the error with an icon inside the evidence list, explains a disabled "Implementado" from the decision itself, and lets the reviewer cite older evidence page by page.
- **The local catalog import works again with signed guide content.** (#351) Requirement attributes are stored in JSON form, so the review dates the owner signed import and reimport cleanly.

### Security

- **A denial-of-service advisory in a development-only lint dependency is closed.** (#211) typescript-eslint moves to 8.73.0, which uses a patched minimatch (GHSA-g3hv-75wg-m249).
- **Stored evidence is kept 365 days under S3 Object Lock in governance mode, and no role may bypass the lock.** (#263) The bucket policy denies the bypass to every principal, the deploy role included; erasing locked evidence is an owner step that CloudTrail records. Any future read or export of a stored file must re-check its sha256.
- **Signing out now ends the session at Cognito too: the refresh token is revoked.** (#324) Cognito's logout revokes no token, so a copied session cookie used to keep working for up to 12 hours after sign-out. Revocation is best effort and never blocks signing out.
- **The sign-in return path now refuses whitespace and control characters itself.** (#325) A return path such as `/<TAB>/evil.example` falls back to `/app` instead of depending on the framework percent-encoding the redirect.

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
