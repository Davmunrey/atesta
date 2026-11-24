# ADR-017: A separate operator portal manages customer organizations from their metadata only

- Status: proposed (2026-11-24). The owner decided the substance on 2026-11-24, relayed by the
  coordinator; accepting the ADR is the owner's call (AGENTS.md, "Owner decisions").
- Issue: #396. Spec: `docs/specs/operator-portal.md`.
- Amends: ADR-012 (amendment 8, proposed with this ADR). Builds on ADR-001, ADR-007, ADR-008,
  ADR-009 (amendments 2 and 3), ADR-012 (amendment 3) and the organization-closure spec.

## Context

The Atesta team has no tool to manage customer organizations:
- **Plans:** an operator sets a plan with raw SQL as the migration role (billing-entitlements
  spec). That role owns every table and bypasses RLS, so the person setting a plan can read every
  customer's content.
- **Erasure:** a command-line tool, `apps/api/devtools/erase_org.py`, run with the same
  credentials (ADR-012 amendment 3).
- **Missing:** nobody can record billing details, suspend an organization, or see which
  organizations exist and whether their connections are healthy.

### Owner decisions, 2026-11-24, relayed by the coordinator

1. **Visibility: metadata only.** Staff see an organization's name, plan and add-ons, billing
   details, member count, usage counters, connection health (status only), created and
   last-activity dates. Never assessments, evidence, incidents, policies, documents, findings,
   scan results or any customer content.
2. **Actions:**
   - (a) set an organization's plan and add-ons, and store its billing details (legal name,
     NIF/VAT ID, billing address, billing contact email);
   - (b) suspend and reactivate an organization: data kept, members cannot use the app while it
     is suspended;
   - (c) export an organization's data and close or erase it, reusing the erasure tool and the
     organization export and closure feature, not duplicating them.
3. **Customer onboarding is self-service** ("lo demás va a ser un auto onboarding"). Customers
   sign up, create their organization and invite their own people. The portal does not create
   organizations or invite customer admins.
4. **A separate application** (for example `admin.atesta.cloud`):
   - its own staff sign-in, in an identity pool separate from customers;
   - mandatory MFA;
   - its own database role;
   - not a section of the customer app. A compromise of the customer app must not expose the
     portal.
5. **A team with roles:** admin (everything), billing (plan, add-ons, billing details), support
   (read-only metadata). Least privilege.

Also decided:
- **No payment gateway** (ADR-009 amendment 3, PR #395). The portal stores billing details and
  issues no invoices.
- **Owner requirement, 2026-11-24, relayed by the coordinator:** "the product must never feel
  like a Frankenstein". The portal is a separate deployment that reuses the console's design
  system and UI code:
  - tokens, DESIGN.md rules and shared components;
  - i18n conventions (ES first, EN second);
  - the same API conventions and error envelope.
  - No new visual language, no second component library, no copied-and-forked components.

## Options weighed

### Where the portal's API runs

| | A. Routes in the existing API (`/operator/*`) | B. A separate API service from the same codebase |
| --- | --- | --- |
| ADR-001 (Python, FastAPI, static Next.js) | Holds | Holds |
| ADR-008 (one codebase, modules through `api.py`) | Holds | Holds. The worker already is a second deployable of the same monolith; the operator service is a third entrypoint, not a microservice with its own domain model |
| Owner decision 4 | Fails. The customer API process would hold the operator database credential and trust the staff identity pool, so remote code execution or SSRF in the customer API reaches the portal | Holds. The customer API's task has no operator secret, and its image has no operator routes |
| Cost | None | One more small Fargate service and a target group |
| Deploys | One | The operator service deploys with the same workflow and image build, from the same commit |

**Choice: B.** Only B meets decision 4. Its cost is one small service, and ADR-008's boundaries
stay as they are.

### How the UI code is shared

| | 1. A second build target inside `apps/web` | 2. A shared package `@atesta/ui`, and a second Next.js app |
| --- | --- | --- |
| One source for tokens and components | Yes | Yes: the components move into the package, they are not copied |
| What each bundle holds | Next.js builds one `app/` directory, so separating the targets needs file-naming tricks (`pageExtensions`), and a mistake ships operator screens in the customer export | Each app ships only its own routes. The customer bundle holds no operator route, and the reverse |
| CSP and origin | One static export serves two origins with different `connect-src` | Each app builds its own CSP with the shared `scripts/csp.ts` |
| Cost | Small now, growing with every screen | A one-time move of the shared set into a package, as its own pull request before the portal UI |

**Choice: 2.**
- **Package:** `packages/ui` (`@atesta/ui`) holds the shared set:
  - `tokens.css`, the font files and the base styles;
  - `page-frame` (`Loading`, `LoadError`, `Empty`), buttons, fields, data tables and state
    badges;
  - the error message component, the locale switcher and `lib/format.ts`;
  - the API error envelope helper and the CSP script.
- **Two apps:** `apps/web` and the new `apps/operator-web` both import the shared set from the
  package.
- **Workspace:** the pnpm workspace moves from `apps/web` to the repository root.
- **DESIGN.md:** stays the single design document. A component the portal needs is added to the
  shared set and documented there, never built inside `apps/operator-web`.

## Decision

### Deployment

- **Two new parts:**
  - an API service, Python package `apps/operator` (`atesta_operator`), with its own image,
    ECS service and target group;
  - a static Next.js export, `apps/operator-web`, in its own private S3 bucket behind its own
    CloudFront distribution, on its own hostname (for example `admin.atesta.cloud`).
- **Single origin, like the console (ADR-007 amendment 2):** the distribution sends `/api/*`
  and `/auth/*` to the operator target group, with no caching.
- **Reaching the target group:** only through the admin distribution. The infrastructure spec
  picks one of two at build time:
  - a listener rule on a custom origin header that only that distribution sends (its value a
    secret in Secrets Manager);
  - a separate load balancer.
- **Images:**
  - The customer API image does not contain `atesta_operator`. A test asserts it.
  - The operator image contains `atesta_api`, because it calls the modules' `api.py`.
- **Credentials, never shared:** the operator service has its own database credential, session
  key and Cognito app client. The customer API and the worker hold none of them, and the reverse.
- **Region:** everything runs in eu-south-2 (ADR-007). No new EU exception:
  - Staff email goes through the Cognito email path already listed in ADR-007 amendment 1.
  - CloudFront transit is the case accepted in amendment 2, with the same conditions.

### Code boundaries (ADR-008)

- **What `atesta_operator` may import:**
  - `atesta_api.modules.<module>.api`;
  - `atesta_api.platform.db` and `atesta_api.platform.audit`.
- **What it may not import:** any module's internals, or `atesta_api.platform.tenancy`. It never
  sets a tenant context.
- **What `atesta_api` may not import:** `atesta_operator`.
- **Enforced** by import-linter contracts.
- **Module functions:** each module adds the operator functions it owns to its `api.py`, for
  example `billing.api.set_subscription` and `connections.api.health_counts`.
  - They run only on a session of the operator role.
  - They never join another module's tables.
  - The operator service composes their results.

### Staff identity

- **A second Cognito user pool, `atesta-staff`, in eu-south-2.** It is separate from the
  customer pool:
  - no self sign-up; an owner step creates each staff account;
  - email as username;
  - its own app client, Authorization Code with PKCE, and the same BFF pattern as the console:
    a sealed HttpOnly cookie with its own key, host-only, `SameSite=Strict`.
- **MFA is required, and SMS is never offered.** Two options:
  - **Passkeys with user verification required.** Cognito counts a passkey with user
    verification as multi-factor authentication "when your user pool has `FactorConfiguration`
    set to `MULTI_FACTOR_WITH_USER_VERIFICATION`". Passkeys need a feature plan other than Lite
    and the choice-based flow (`USER_AUTH`). Source: AWS Cognito developer guide,
    "Authentication flows", passkey section,
    <https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html>,
    read 2026-11-24.
  - **Password plus TOTP**, the customer pool's setting.
  - **Proposed:** passkeys first, because they resist phishing. Password plus TOTP stays as the
    fallback, because the same page says "the `WEB_AUTHN` option for passkey authentication must
    be accompanied by at least one other option".
  - **Candidate:** the OpenTofu attribute for `FactorConfiguration` in the pinned AWS provider is
    not yet checked. The infrastructure pull request confirms it against the provider docs.
- **Tokens:** the operator API accepts only access tokens of the staff pool's app client, with
  the same checks as identity-auth (issuer, `token_use`, `client_id`, scopes).
  - A customer token gets 401 at the operator API, and a staff token gets 401 at the customer
    API.
- **Roles live in Postgres, not in Cognito groups:** table `operator_staff`, with the role
  `admin`, `billing` or `support`, and `disabled_at`.
  - A valid staff token without an enabled row gets 403.
  - The last enabled admin cannot be disabled or demoted.
- **Sessions:** a session ends after 30 minutes idle and 8 hours in total. Approving an erasure,
  suspending or closing needs a sign-in within the last 15 minutes (`auth_time`).

### Network access: an owner choice

| Option | What it does | Cost and limits |
| --- | --- | --- |
| A. No allowlist | Any network reaches the sign-in page; passkeys and MFA guard it | Nothing to run. Sign-in stays exposed to password spraying, which Cognito throttles |
| B. IP allowlist (proposed if staff have fixed egress addresses) | An AWS WAF web ACL on the admin distribution allows only listed addresses; everything else gets 403 at the edge | WAF is in AWS's ENS High scope (hosted-environment spec). A web ACL for CloudFront is created in us-east-1; it is configuration and holds no customer data. A staff member away from the listed networks cannot work |
| C. Private access (VPN or AWS Verified Access) | The portal has no public endpoint | The most isolation, at the highest cost and setup. Availability in eu-south-2 is not checked |

The ADR does not pick. Whatever the owner chooses, the portal enforces MFA and roles on its own.

### Database: one role, a closed list of columns, no content

- **New login role `atesta_operator`:** NOSUPERUSER and NOBYPASSRLS, owns nothing, member of no
  role.
- **Tenant context:** it never sets one, and it reads across organizations by design. What keeps
  it away from content is grants, not the tenant setting. ADR-012 amendment 8 records this.
- **How it reads metadata:** each table on a closed list gets two things:
  - column-level SELECT on named columns only;
  - one named policy, `operator_metadata_read`, `FOR SELECT TO atesta_operator USING (true)`.

  Every other tenant table, content tables included, gives the role no privilege at all, so a
  bug in the operator code cannot read content: Postgres refuses it. The schema linter keeps a
  grants snapshot for this role, as it does for `atesta_app`.
- **Why not SECURITY DEFINER functions:** a definer function runs as its owner. ADR-012 bans
  them because they are the way around RLS and grants that the linter cannot see into. Column
  grants keep the boundary in the catalog, where the existing linter already reads it (`attacl`).
- **Why not views:** ADR-012 requires `security_invoker` views. Such a view checks the caller's
  privileges on the base tables, so it would need the same column grants and add nothing.
- **Writes, each held by a column grant and one named policy `TO atesta_operator`:**
  - `subscriptions` (INSERT, UPDATE): plan, add-ons, note;
  - `billing_profiles` (INSERT, UPDATE): a new tenant table, below;
  - `organizations` (UPDATE of the suspension and closure columns only);
  - `audit_events` (INSERT), where the policy's `WITH CHECK` allows only an `operator.*` action
    with no `actor_user_id`.
- **Operator tables** (ADR-012 amendment 3 class): no RLS, no privilege for `atesta_app`.
  - `operator_staff`;
  - `operator_audit_events`, append-only;
  - `erasure_requests`.
- **No content, ever:** content tables get no privilege, and nothing exists outside this list
  for content. No break-glass path and no BYPASSRLS role are added.

### What staff can do

- **Read:** the metadata in owner decision 1, field by field as listed in the spec, each with
  its source column.
- **Set the plan and add-ons:** a write to `subscriptions`. It replaces the raw SQL in the
  billing-entitlements spec, which stays in the runbook only as the fallback while the portal is
  not deployed. Access checks still go only through `billing.api` (ADR-009).
- **Billing details:** a new tenant table, `billing_profiles`, one row per organization:
  - **Columns:** legal name, tax ID, address, billing contact email.
  - **Who reads and writes:** `atesta_app` may only read it. The organization's owners see it,
    read-only, in the console.
  - **Erasure** deletes it with the other tenant tables. Retention under Spanish tax law is an
    open question for the owner's adviser.
- **Suspend and reactivate:** two new columns on `organizations`, `suspended_at` and
  `suspension_reason`, the latter a code from a closed list.
  - **While suspended,** `identity.api.require_member` refuses every route with 403
    `identity.organization_suspended`, except what the spec allows, so that GDPR Art. 20 keeps
    working:
    - `/me`;
    - the owners' export, closure and billing-details routes.
  - API keys and the MCP server get the same refusal.
  - **Worker:** it enqueues no scan or notification for a suspended organization, apart from the
    suspension notices.
  - **Data:** nothing is deleted or changed.
- **Export:** staff never receive customer data. "Export" in the portal asks the owners to export:
  - it notifies them by email;
  - it records the request in their Activity. The export itself stays the existing owner-only one.

  This keeps owner decision 1 and the offboarding runbook's rule, "Atesta staff never download
  it on the customer's behalf".
- **Close:** an admin can start the existing closure for an organization:
  - It sets `closure_requested_at`, with the origin `operator`.
  - Every member sees the same banner and the same 30-day date as an owner-requested closure.
  - Only an admin cancels a closure the operator started.
- **Erase:** the portal records an erasure request; it never deletes.
  - **Approval:** a second admin approves it. The spec proposes this two-person rule and flags it.
  - **Execution:** an erasure runner, a one-off ECS task with the migration credential, runs the
    existing `erase_organization` for approved requests whose closure date has passed. The task
    is scheduled, and is the only holder of that credential outside deploys.
  - **Reuse:** `erase_org.py` gains `--request <id>`, which also checks the approval. There is
    one erasure implementation.
  - **Candidate:** the scheduler's availability in eu-south-2 is not checked. Until it is, an
    admin runs the same command by hand from the runbook.
- **What the portal cannot do:**
  - **Onboarding (owner decision 3):** no creating organizations, inviting people or changing
    members.
  - **Payments (ADR-009 amendment 3):** no invoices and no payments.

### Audit: two trails

- **`operator_audit_events` (operator table, append-only):** every write and every view of an
  organization's detail page. Each row holds:
  - the staff member's id and role at that moment;
  - the action;
  - the organization id;
  - the reason the staff member gave (required for every write);
  - the request id.

  It never holds customer content. It holds billing values as "changed", not as old and new
  values. It outlives erasure, like `erasure_receipts`.
- **The customer's own `audit_events`:** every write that changes the organization, with
  `actor_user_id` NULL and an `operator.*` action, in the same transaction as the write. The
  console's Activity page (admins and owners) shows these as done by "the Atesta team". The
  customer sees what changed, never the staff member's name. The operator trail links the two
  through the request id, and the owner can ask Atesta who acted.
- **Which actions the customer sees:**
  - plan and add-on changes;
  - billing details updated (field names only);
  - suspended (with the reason code), and reactivated;
  - closure started or cancelled by the operator;
  - export requested;
  - erasure requested, approved or cancelled.
- **Which actions the customer does not see:** reads (list, detail views). They change nothing,
  and showing every support lookup would bury the events that matter. They are in the operator
  trail. Whether customers may receive that log on request is an open question in the spec.

### What is ruled out

- **No break-glass.** No staff role, flag or emergency procedure reads customer content through
  the portal. When a support case needs content, the customer shares it, through their own
  export or by showing it.
- **No impersonation.** No "view as" or "sign in as" a customer member, and no session for a
  staff member in the customer app on the strength of the portal.
- **Data minimisation (GDPR Art. 5(1)(c)):**
  - The portal stores only the billing details and staff identities.
  - It shows member counts, never member names or emails.
  - It never shows connection display names, tenant ids or domains.
  - A tax ID can be personal data (a sole trader's NIF). It is shown in full only to admin and
    billing.

### Design system

- **Same design for staff and customers:** the portal uses the console's Operate mode and the
  identity in DESIGN.md.
- **Only shared pieces:** every portal screen is built from `@atesta/ui` tokens and components.
- **Environment marker:** the portal shell names itself "Portal de operaciones / Operations
  portal" in its header, using existing tokens, so staff never mistake it for the console.
- **API conventions:** the operator API uses the console's error envelope
  (`{"detail": {"code": ...}}`, codes namespaced `operator.*`). It publishes its own OpenAPI
  document, from which `apps/operator-web` generates its typed client with the same script.

## Consequences

- **Exposure:** a compromise of the customer API, web app or worker exposes no operator
  credential. A compromise of the operator service exposes metadata of every organization and the
  power to change plans, suspend and request closure, but no customer content and no erasure
  without a second admin. The spec's threat model lists the residual risks.
- **ADR-012 changes** (amendment 8, proposed):
  - a second runtime role;
  - role-scoped named policies;
  - a new tenant table;
  - three operator tables;
  - a second grants snapshot.
- **One more service:** another ECS service, distribution, user pool and image to run and patch.
  A small monthly cost; no price appears in the repository (ADR-015).
- **UI code move:** the shared UI moves to `packages/ui` before the portal UI is built. That is
  a refactor of `apps/web` with no visual change, checked by the existing tests and e2e.
- **Default plan:** self-onboarded organizations keep today's default plan (`business`) until
  the owner answers the default-plan and trial question in the spec.
- **Customer-facing documents:** the DPA and the security page must state that Atesta staff see
  organization metadata, never content, and that operator actions appear in the customer's
  activity. That is a follow-up for the legal pages, not part of this ADR.
