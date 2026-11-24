# Runbook: Google Workspace connections (owner)

Covers the owner's steps for Google Workspace (issue 421): the one-time setup, then each customer
from start to verification, key rotation and disconnection. Sources: scanner-connectors spec
(Google Workspace onboarding, Credentials, D7 to D9, Owner steps). No agent can take these steps.

Every Google page below was read on 2026-11-24; the sources and their dates are at the end.
Anything not yet tried against a real Google organization is marked **candidate**.

## Rules for this runbook

- **No key leaves its place.**
  - `google_sa.sh` writes a new key only to a RAM disk it creates and destroys, then into the
    credential store.
  - A key never goes into a chat, an issue, a pull request, the repository, a note, an email
    or a screenshot.
  - The script never prints one.
- **Read-only.**
  - The customer authorizes exactly the scopes the script prints (AGENTS.md rule 1).
  - Never add `apps.licensing`, `apps.alerts`, `apps.groups.settings` or
    `admin.directory.user.security`: Google describes each as manage or delete access (D6).
- **Where keys are stored.**
  - For now keys go to the local credential store: dev only, a folder outside any repository,
    mode 700, files mode 0600. Atesta does not encrypt it; on a Mac, FileVault protects it at rest.
  - Production keys go to AWS Secrets Manager under a KMS key. That path is added in the infra
    session (owner, 2026-11-24).
- **One pair per organization.** Each Atesta organization gets its own scan and verifier service
  accounts (D7). One shared client would let one customer's admin authorize another customer's
  reads.

## 0. What you need

| Need | Note |
|---|---|
| A Mac with the Google Cloud CLI (`gcloud`) signed in as you | `gcloud auth login` |
| `uv` and a checkout of the Atesta repository | The script runs `atesta-register-google` from it (PR #404) |
| A Google Cloud organization for Atesta | A Google Cloud organization exists for a Google Workspace or Cloud Identity account. If Atesta has neither, sign up for Cloud Identity Free on a domain Atesta owns and verify it by DNS (**candidate**: confirm at sign-up) |
| The local credential store | `mkdir -m 700 ~/atesta-secrets`, outside every repository. The worker reads it as `ATESTA_SCAN_CREDENTIALS_DIR` |

## 1. One-time: the dedicated project

```bash
gcloud projects create atesta-dev-scanners --organization ORG_ID
```

```bash
gcloud services enable admin.googleapis.com cloudidentity.googleapis.com --project atesta-dev-scanners
```

- **APIs to enable:** only the Admin SDK API and the Cloud Identity API, in the project that holds
  the service accounts. Prowler's Google Workspace guide lists exactly these two.
- **API never to enable:** the Licensing API (`licensing.googleapis.com`), because of D6.
- **What the project holds:** the service accounts only, with no Workspace data. Use
  `atesta-prod-scanners` for production.

## 2. One-time: allow keys in this project only

- **Why this step:** Google enforces `iam.managed.disableServiceAccountKeyCreation` on every
  organization created on or after 3 May 2024. While it holds, `google_sa.sh` stops at the first key
  ("gcloud could not create a key").
- **Google's recommendation:** keep the block for the whole organization and exempt only this
  project, with a tag.

1. Look at what is enforced:

   ```bash
   gcloud org-policies list --organization ORG_ID
   ```

2. Create the tag and its two values:

   ```bash
   gcloud resource-manager tags keys create disableServiceAccountKeyCreation --parent organizations/ORG_ID
   ```

   ```bash
   gcloud resource-manager tags values create enforced --parent ORG_ID/disableServiceAccountKeyCreation
   ```

   ```bash
   gcloud resource-manager tags values create not_enforced --parent ORG_ID/disableServiceAccountKeyCreation
   ```

3. Tag the organization `enforced` and the project `not_enforced`. `PROJECT_NUMBER` is in
   `gcloud projects describe atesta-dev-scanners`:

   ```bash
   gcloud resource-manager tags bindings create --tag-value ORG_ID/disableServiceAccountKeyCreation/enforced --parent //cloudresourcemanager.googleapis.com/organizations/ORG_ID
   ```

   ```bash
   gcloud resource-manager tags bindings create --tag-value ORG_ID/disableServiceAccountKeyCreation/not_enforced --parent //cloudresourcemanager.googleapis.com/projects/PROJECT_NUMBER
   ```

4. Make the policy follow the tag.
   - Write this to `policy.yaml`. It is not a secret, so a normal disk is fine.
   - Use one file per constraint that step 1 showed as enforced: the managed
     `iam.managed.disableServiceAccountKeyCreation` and, if present, the older
     `iam.disableServiceAccountKeyCreation`.

   ```yaml
   name: organizations/ORG_ID/policies/iam.managed.disableServiceAccountKeyCreation
   spec:
     rules:
       - condition:
           expression: "resource.matchTag('ORG_ID/disableServiceAccountKeyCreation', 'not_enforced')"
         enforce: false
       - enforce: true
   ```

   ```bash
   gcloud org-policies set-policy policy.yaml
   ```

5. Check that the project is exempt and that the rest of the organization is not:

   ```bash
   gcloud org-policies describe iam.managed.disableServiceAccountKeyCreation --project atesta-dev-scanners --effective
   ```

**Candidates:**
- Google's keys page shows this tag-based rule for the older constraint. Whether the managed
  constraint takes the same conditional rule is a candidate.
- The definitive check is step 3 of the next section: `google_sa.sh create` succeeding.

## 3. Each customer

1. **The customer creates the connection** in Atesta. It starts as "Pendiente de preparación"
   (`pending_provisioning`). Copy the organization id and the connection id from the connection page.
2. **You create the two service accounts and their keys:**

   ```bash
   scanner/runbooks/google_sa.sh create --project atesta-dev-scanners --org ORG_ID --connection CONNECTION_ID --store ~/atesta-secrets
   ```

   The script does the following:
   - creates `scan-…` and `verify-…` in the project, or reuses them;
   - writes one key each on a RAM disk;
   - stores the keys as `google-ORG_ID.json` and `google-verifier-ORG_ID.json` (mode 0600);
   - deletes any older key those accounts had;
   - destroys the RAM disk;
   - runs `atesta-register-google`, which needs `ATESTA_DATABASE_URL` set as for the worker.

   The connection becomes `pending_setup`. The script ends by printing two client IDs, each with
   its scope string.
3. **The customer authorizes both clients** (until the onboarding screen ships, send them the
   two printed lines).
   - A super admin opens Admin console, Security, Access and data control, API controls, Manage
     Domain Wide Delegation, Add new.
   - They add one entry per client ID with exactly its scope string.
   - If multi-party approval is on, a second super admin approves.
4. **The customer names the super admin** Atesta reads as. An existing super admin is the
   recommendation (owner, 2026-11-24). The primary domain comes from that email. This step needs
   the onboarding screen, which comes after the console unification pass.
5. **The customer selects Verificar.** Google says a delegation can take up to 24 hours to reach
   every user. Until then the connection stays "Verificando" and Atesta tries again every hour.

## 4. Every 90 days: rotate the keys (D9)

```bash
scanner/runbooks/google_sa.sh rotate --project atesta-dev-scanners --org ORG_ID --store ~/atesta-secrets
```

A new key per account replaces the stored one, then every older key is deleted. The connection
does not change: rotation changes no client ID and no reference. Google allows at most 10 keys per
service account, so never skip the delete.

## 5. Disconnect: disable both accounts

Run this when the organization's last Google connection becomes `disconnected` or `revoked`
(onboarding step 5):

```bash
scanner/runbooks/google_sa.sh disable --project atesta-dev-scanners --org ORG_ID --store ~/atesta-secrets
```

It deletes every key of both accounts, disables both, and removes the stored keys. Also tell the
customer to delete the two delegation entries; Google stops dependent apps at once.

## 6. The Workspace test tenant (live golden Google, PR 12)

1. Sign up a Google Workspace subscription that plays the customer, on a domain you can verify.
   The account that signs up is its first super admin; turn on 2-Step Verification for it.
2. In Atesta (dev), create a Google connection in a test organization and follow section 3.
3. Record which candidates in the spec the run closes, with dates. See the spec's "Candidates"
   rows for Google, such as `API_SCOPES` after an edit, or `uniqueId` against `client_id`.

## If something fails

| Symptom | Cause and fix |
|---|---|
| `could not create a key … key-creation block` | Section 2 is missing or not effective for this project |
| `is not memory (tmpfs)` or `could not create a RAM disk` | Run on a Mac or Linux machine; on Linux `/dev/shm` must be tmpfs |
| `the store … is inside a repository` or `readable by you only` | Use a folder outside every repository, `chmod 700` |
| `this org already has stored keys` | The organization is set up: use `rotate`, or `disable` first |
| `not a Google one waiting for provisioning` | The connection is not `pending_provisioning`; check its id, and that it is Google |
| `not this org's Google secret` | The `--org` given does not match the connection's organization |

## Sources (read 2026-11-24)

| Fact | Source |
|---|---|
| Organizations created on or after 3 May 2024 enforce `iam.managed.disableServiceAccountKeyCreation` | https://docs.cloud.google.com/resource-manager/docs/manage-baseline-constraints (updated 2026-11-12) |
| Exempt a project from key-creation with a `disableServiceAccountKeyCreation` tag and a conditional policy; `gcloud iam service-accounts keys create` writes the private key to the given file | https://docs.cloud.google.com/iam/docs/keys-create-delete (updated 2026-11-17) |
| A service account id has 6 to 30 lowercase letters, digits and dashes, and a permanent numeric unique id | https://docs.cloud.google.com/iam/docs/service-accounts-create (updated 2026-11-17) |
| `gcloud iam service-accounts disable` | https://docs.cloud.google.com/iam/docs/service-accounts-disable-enable (updated 2026-11-17) |
| `keys list --managed-by`, `describe` (a missing account answers PERMISSION_DENIED), `tags keys/values/bindings create`, `org-policies set-policy` and `describe --effective`, `projects create --organization` | https://cloud.google.com/sdk/gcloud/reference (the pages for each command) |
| The Admin SDK API and the Cloud Identity API in the service account's project; Licensing optional | https://docs.prowler.com/user-guide/providers/googleworkspace/authentication |
| Domain-wide delegation path, multi-party approval, up to 24 h propagation | Spec, Facts checked (knowledge.workspace.google.com, control-api-access-with-domain-wide-delegation) |
| 10 keys per service account | Spec, Facts checked (docs.cloud.google.com/iam/quotas) |
