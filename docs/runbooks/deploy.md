# Runbook: deploy Atesta to AWS

The owner's one-day path from no AWS account to a running environment (hosted-environment spec,
issue #220). Do dev first, end to end; prod repeats the same steps in its own account.
Everything here is code in `infra/` and `.github/workflows/deploy.yml`; nothing has been applied.

## 0. Decide before you start

| Decision | Why it blocks | Where |
|---|---|---|
| CloudFront in front of the API, or not | Edge locations are global; the app is single-origin, so it routes `/api` and `/auth` through the same distribution. Accept it in ADR-007 amendment 1, or choose another option | PR #254, "For the owner" |
| ECS on Fargate under ENS High | The ENS High scope lists ECS but not Fargate by name. Check the certificate in AWS Artifact (needs an account) | hosted-environment spec, "Still open" |
| The domain | Certificates, CloudFront aliases, the Cognito callback and SES all need it | below |

## 1. Accounts (owner only)

1. Create an AWS Organization with a management account, then two member accounts: `atesta-dev`
   and `atesta-prod`. Sign in through IAM Identity Center, never with root keys.
2. In each member account, **enable the eu-south-2 (Spain) region**. It is an opt-in region.
   eu-west-3 (Paris, prod only, for Cognito email) and us-east-1 (CloudFront certificate) are on
   by default.
3. In each account, create the OpenTofu state bucket in eu-south-2. Name it something like
   `atesta-<env>-tofu-state-<account id>`, with versioning on, public access blocked and SSE on.

## 2. First apply from your laptop (base layer)

With Identity Center credentials for the account, and OpenTofu 1.13.9 (`infra/.opentofu-version`):

```bash
cd infra/envs/dev
tofu init -backend-config="bucket=<state bucket>"
tofu apply -var state_bucket=<state bucket> -var budget_email=<alerts address>
```

**This creates:**
- the keys, the network and the evidence bucket;
- the database and its secrets;
- the registries, Cognito (the customer pool and the operator portal's staff pool), the GitHub
  roles and the budget alerts.

It creates no ECS service and no CloudFront yet: `images` and `edge` are still unset. Note the
outputs `deploy.repositories` and `github_oidc` (the plan and apply role ARNs).

In prod, also pass these. The Cognito email identity is created in eu-west-3, and
`platform.cognito_dns` lists its DNS records.

```bash
-var app_url=https://app.<domain>
-var admin_url=https://admin.<domain>
-var cognito_mail_domain=<domain>
-var cognito_from="Atesta <no-reply@<domain>>"
```

## 3. Domain, certificates and DNS

1. Request two ACM certificates, with DNS validation:
   - **CloudFront:** in **us-east-1**, for `app.<domain>`, and one for `admin.<domain>` (the
     operator portal, ADR-017). They are certificates only; no customer data goes there.
   - **API load balancer:** in **eu-south-2**, for `api-origin.<domain>`, the hostname CloudFront
     uses to reach it.
2. Publish the validation CNAMEs, plus the SES records from the outputs: DKIM, MAIL FROM and
   DMARC (`mail_dns_records`, `cognito_dns`).
3. Create the `security@<domain>` mailbox, or an alias that reaches the owner, and send it a
   test message. Every deploy publishes that address in `/.well-known/security.txt`
   (`docs/specs/security-txt.md`); a vulnerability report sent to a mailbox that does not exist
   is lost.
4. After the first deploy (step 6), point the hostnames:
   - `app.<domain>`: CNAME or alias to the CloudFront domain (output `platform.web.domain`);
   - `api-origin.<domain>`: alias to the load balancer (output `platform.api_load_balancer`);
   - `admin.<domain>`: CNAME or alias to the portal's CloudFront domain (output
     `platform.admin_web.domain`).

## 4. Secrets (never in git, never in shell history)

Generate three passwords and write the connection URLs: the app, the migrations and the operator
service (ADR-017). Work in a tmpfs or with `umask 077`, and delete the files afterwards:

```bash
host=$(tofu output -json platform | jq -r .database_endpoint)
for role in app migration operator; do
  case $role in app) user=atesta_app;; migration) user=atesta_owner;; operator) user=atesta_operator;; esac
  pass=$(aws secretsmanager get-random-password --exclude-punctuation --password-length 40 --query RandomPassword --output text)
  printf 'postgresql+psycopg://%s:%s@%s:5432/atesta' "$user" "$pass" "$host" > "/dev/shm/$role-url"
  aws secretsmanager put-secret-value --secret-id "atesta/atesta-dev/db/$role-url" --secret-string "file:///dev/shm/$role-url"
  rm "/dev/shm/$role-url"
done
head -c 32 /dev/urandom | base64 > /dev/shm/session-key
aws secretsmanager put-secret-value --secret-id atesta/atesta-dev/api/session-key --secret-string file:///dev/shm/session-key
head -c 32 /dev/urandom | base64 > /dev/shm/session-key  # a different key for the operator portal
aws secretsmanager put-secret-value --secret-id atesta/atesta-dev/operator/session-key --secret-string file:///dev/shm/session-key
rm /dev/shm/session-key
```

On macOS, use a directory created with `mktemp -d` instead of `/dev/shm`, and remove it
afterwards.

**Operator portal origin header** (ADR-017, "Reaching the target group"). The portal's
distribution sends it, and the load balancer forwards to the operator service only requests that
carry it. Letters and digits only. Set it before `edge`, because OpenTofu reads it when `edge`
is set:

```bash
aws secretsmanager get-random-password --exclude-punctuation --password-length 64 \
  --query RandomPassword --output text > /dev/shm/origin-header
aws secretsmanager put-secret-value --secret-id atesta/atesta-dev/operator/origin-header --secret-string file:///dev/shm/origin-header
rm /dev/shm/origin-header
```

To rotate it, put a new value and run the deploy: the distribution and the listener rule change
in the same apply, so the portal may answer 404 for a minute.

**M365 scanner credential** (scanner-connectors spec, AWS runner; issue 453). The "Atesta
Scanner" app's client id and its certificate go in `atesta/<env>/m365/scanner` as JSON, with the
same keys as a local credential file. `M365_CERTIFICATE_CONTENT` is the passwordless PFX in
base64 on one line. Write the files in the tmpfs, never on the command line:

```bash
openssl base64 -A -in /dev/shm/scanner.pfx > /dev/shm/scanner.b64
jq -n --arg id "<scanner app client id>" --rawfile cert /dev/shm/scanner.b64 \
  '{AZURE_CLIENT_ID: $id, M365_CERTIFICATE_CONTENT: $cert}' > /dev/shm/m365-scanner
aws secretsmanager put-secret-value --secret-id atesta/atesta-dev/m365/scanner --secret-string file:///dev/shm/m365-scanner
rm /dev/shm/m365-scanner /dev/shm/scanner.b64 /dev/shm/scanner.pfx
```
**Alerts.** The first apply subscribes the budget address to `<env>-alerts`. AWS emails a
confirmation link to that address; click it once, or the scan failure-rate alarm reaches nobody.

## 5. GitHub environments

1. In the repository settings, create the environments `dev` and `prod`:
   - required reviewers: you;
   - deployment branches: `main` only.
2. In each environment, set:
   - **Variables:**
     - `AWS_APPLY_ROLE_ARN`: the `atesta-<env>-apply` role.
     - `TOFU_STATE_BUCKET`.
     - `TFVARS_JSON`: the non-secret settings, for example:

       ```json
       {
         "edge": {
           "aliases": ["app.<domain>"],
           "admin_aliases": ["admin.<domain>"],
           "web_certificate_arn": "<us-east-1 certificate ARN>",
           "admin_certificate_arn": "<us-east-1 certificate ARN for admin.<domain>>",
           "api_origin_domain": "api-origin.<domain>",
           "api_certificate_arn": "<eu-south-2 certificate ARN>",
           "content_security_policy": "filled in by the workflow",
           "admin_content_security_policy": "filled in by the workflow"
         },
         "app_environment": {
           "ATESTA_ENV": "dev",
           "ATESTA_WEB_ORIGIN": "https://app.<domain>",
           "ATESTA_WEB_BASE_URL": "https://app.<domain>",
           "ATESTA_COGNITO_REGION": "eu-south-2",
           "ATESTA_COGNITO_USER_POOL_ID": "<output>",
           "ATESTA_COGNITO_APP_CLIENT_ID": "<output>",
           "ATESTA_COGNITO_DOMAIN": "<output>"
         },
         "mail_domain": "<domain>"
       }
       ```

       Prod also adds `app_url`, `admin_url`, `cognito_mail_domain` and `cognito_from`. Both add
       `"staff_passkeys": true` only after the passkey step below.
   - **Secret:** `BUDGET_EMAIL`.
3. Update the Cognito callback and logout URLs to `https://app.<domain>` in dev too, by setting
   them in `envs/dev/main.tf`, in a PR.
4. Require the `images` check in the live main-branch ruleset. The repository copy,
   `.github/rulesets/main-branch.json`, already lists it.

## 6. First deploy

1. **Actions → deploy → Run workflow → dev**, from `main`. The workflow:
   - builds and pushes the images, and builds the web app with its CSP;
   - creates the cluster, the migration task and the task egress;
   - runs the migrations and stops if their exit code is not 0;
   - applies everything else;
   - uploads the site;
   - checks that the response has a CSP and HSTS, that `/api/v1/me` answers 401 and that
     `/.well-known/security.txt` is served as UTF-8 text.

   On this first run, the migrations fail because the roles do not exist yet. That is expected:
   go to step 2.
2. **Bootstrap the database once**, with the bootstrap task. It runs `bootstrap.sql` as the RDS
   master and sets each role's password from its URL secret. The values come from the `deploy`
   output.

   ```bash
   aws ecs run-task --cluster <deploy.cluster> --launch-type FARGATE \
     --task-definition <deploy.bootstrap_family> \
     --network-configuration "awsvpcConfiguration={subnets=[<deploy.private_subnets>],securityGroups=[<deploy.app_security_group>],assignPublicIp=DISABLED}"
   ```

   Its log (`/atesta/atesta-dev/migrate`, stream prefix `bootstrap`) ends with
   `bootstrap done; LOGIN set for atesta_app, atesta_operator, atesta_owner`.
3. Run the deploy workflow again. This time the migrations and the smoke check pass. The smoke
   check also proves the portal's routing: `/api/v1/staff` answers 401 on `admin.<domain>` (the
   operator service) and 404 on `app.<domain>` (the customer API).
4. Point DNS (step 3.4), sign up at `https://app.<domain>` with MFA, and walk the pilot guide's
   first steps.

## 6b. Operator portal checks (first apply)

The operator portal's infrastructure (operator-portal spec, build step 6) is part of the same
apply. Before relying on it:

1. **The staff pool requires MFA and never SMS.** The operator service checks this at startup and
   refuses to start otherwise. If its tasks keep failing (ECS service events, log group
   `/atesta/<env>/operator`), compare with:

   ```bash
   aws cognito-idp get-user-pool-mfa-config --user-pool-id <staff_cognito.user_pool_id>
   ```

   Expect `"MfaConfiguration": "ON"`, `"SoftwareTokenMfaConfiguration": {"Enabled": true}`, no
   `SmsMfaConfiguration`, and `"WebAuthnConfiguration"` with `"UserVerification": "required"`.
   Note the `RelyingPartyId` it shows: this has not been seen yet on a real pool.
2. **The service is healthy:** the target group `<env>-operator` has one healthy target, and
   `https://admin.<domain>/` shows *Iniciar sesión*.
3. **The first admin:** `operator-staff.md`, section 1.
4. **Passkeys (once, after the first admin signs in).** The pinned provider cannot set
   `FactorConfiguration`, and with MFA required Cognito offers passkeys only when it is
   `MULTI_FACTOR_WITH_USER_VERIFICATION` (spec, "Infrastructure as built"). Set it with the
   complete MFA settings, because the call replaces them:

   ```bash
   aws cognito-idp set-user-pool-mfa-config --user-pool-id <staff pool id> \
     --mfa-configuration ON --software-token-mfa-configuration Enabled=true \
     --web-authn-configuration UserVerification=required,FactorConfiguration=MULTI_FACTOR_WITH_USER_VERIFICATION
   ```

   Read it back with `get-user-pool-mfa-config`, then add `"staff_passkeys": true` to
   `TFVARS_JSON` and deploy. If a later change to the staff pool's MFA arguments is applied, the
   provider resets the field, and passkeys stop being offered while password plus authenticator
   app still work. Repeat this step after any such change.
5. **The erasure runner:** EventBridge Scheduler shows the schedule `<env>-erasure`. Within
   6 hours the log group `/atesta/<env>/erasure` has a line
   `{"event": "erasure.run", "status": "finished"}`, and the alarm `<env>-erasure-runner` is OK.
6. **Alarms reach someone:** the alerts subscription is confirmed (step 4, "Alerts"). The alarms
   `<env>-operator` and `<env>-erasure-runner` are in OK state.
7. **Malware scanning:** the GuardDuty Malware Protection plan for the evidence bucket is
   `ACTIVE`:

   ```bash
   aws guardduty list-malware-protection-plans
   aws guardduty get-malware-protection-plan --malware-protection-plan-id <id> --query Status
   ```

## 7. Every later deploy

Merge to `main`, then run the deploy workflow for the environment. The reviewers you set in
step 5 approve each run.

**Once, before the first deploy that carries migration 0033 (operator portal, #445):** run the
bootstrap task of step 6.2 again. It adds the `atesta_operator` role (no LOGIN yet), which
`atesta_owner` cannot create; the other roles keep their passwords. Without it, migration 0033
stops with "role atesta_operator does not exist" and the running version stays. From #499 the
task also gives `atesta_operator` its login, so write `atesta/<env>/db/operator-url` first
(step 4); a secret without a value stops the task before it starts.

**Order for the first deploy with the operator portal:**
1. Write `atesta/<env>/db/operator-url`, `atesta/<env>/operator/session-key` and
   `atesta/<env>/operator/origin-header` (step 4).
2. Add the admin fields to `edge` in `TFVARS_JSON`, and `admin_url` in prod (step 5).
3. Run the bootstrap task (step 6.2). Its log ends with
   `LOGIN set for atesta_app, atesta_operator, atesta_owner`.
4. Run the deploy workflow, then the checks in 6b.

**Migrations run before the services change:**
- If a migration fails, the old version keeps running.
- If new tasks fail their health checks, ECS's circuit breaker rolls the service back to the
  previous task definition.

**The database engine is PostgreSQL 18** (`infra/modules/rds`, #299). RDS applies 18.x minor
versions itself in the Sunday maintenance window. A major upgrade is a planned change of the RDS
module, CI and `compose.yaml` together. On a running instance it also needs a new `postgresN`
parameter group, `allow_major_version_upgrade`, and a manual snapshot taken first.

## 8. Rollback

| What broke | Do |
|---|---|
| New tasks unhealthy | Nothing: the circuit breaker rolls back. Check the service events in the ECS console |
| A bad release that is healthy | Revert the commit on `main`, then run the deploy |
| A bad migration | Migrations go forward only. Write a new migration that undoes it, review it, then deploy. For data loss, restore the database to a point in time (RDS keeps 14 days in dev and 35 in prod) into a new instance, then switch the URL secrets |
| The web app only | Revert and deploy. The site bucket is versioned, so an older object can also be restored by hand |

## 9. Cost estimate (monthly, USD, on-demand)

**Prices:** AWS Price List bulk files for eu-south-2 (CloudFront: global file), publication
`20261111234623`, read on 2026-11-23. The hours assume 730 a month. Usage is a small pilot: a
handful of organizations, one scan a day each. Taxes are not included.

| Item | Unit price | Dev | Prod |
|---|---|---|---|
| Fargate API, 0.25 vCPU and 0.5 GB per task | $0.046552 per vCPU-hour, $0.005112 per GB-hour | 1 task: 10.36 | 2 tasks: 20.72 |
| Fargate worker, 0.5 vCPU and 1 GB | same | 20.72 | 20.72 |
| Fargate scans, 2 vCPU and 4 GB ($0.1136 per hour) | same | 75 h: 8.52 | 150 h: 17.03 |
| Fargate egress proxy, 0.25 vCPU and 0.5 GB per task (issue 454) | same | 1 task: 10.36 | 2 tasks: 20.72 |
| Fargate operator service, 0.25 vCPU and 0.5 GB (ADR-017) | same | 1 task: 10.36 | 1 task: 10.36 |
| Fargate erasure runner, 0.25 vCPU and 0.5 GB, about 1 minute every 6 hours | same | 0.03 | 0.03 |
| Interface endpoints: ecr.api, ecr.dkr, logs, secretsmanager (issue 454) | $0.011 per endpoint-zone hour, plus $0.01 per GB (VPC file, read 2026-11-24) | 1 zone: 32.12 | 2 zones: 64.24 |
| Cloud Map name for the proxy | $0.10 per registered task (Cloud Map file, publication `20261106193843`); $0.50 per hosted zone (Route 53 file, publication `20261118191548`) | 0.60 | 0.70 |
| RDS PostgreSQL db.t4g.micro | $0.018 per hour Single-AZ, $0.035 Multi-AZ | 13.14 | 25.55 |
| RDS gp3 storage, 20 GB | $0.127 per GB-month, $0.254 Multi-AZ | 2.54 | 5.08 |
| RDS backups beyond the database size | $0.095 per GB-month | 0 | about 10 GB: 0.95 |
| NAT gateway | $0.048 per hour plus $0.048 per GB | 1 gateway, 20 GB: 36.00 | 2 gateways, 50 GB: 72.48 |
| Public IPv4 addresses (NAT, load balancer) | $0.005 per hour each | 3: 10.95 | 4: 14.60 |
| Application Load Balancer | $0.0252 per hour plus $0.008 per LCU-hour | about 0.5 LCU: 21.32 | about 1 LCU: 24.24 |
| KMS keys | $1 per key-month (more after rotations) | 5: 5.00 | 5: 5.00 |
| Secrets Manager | $0.40 per secret-month | 8: 3.20 | 13 (with connectors): 5.20 |
| Alerts: scan failure rate, erasure runner, operator (4 custom metrics, 3 alarms on 6 metrics) | $0.30 per metric-month, $0.10 per alarm metric-month (CloudWatch file, publication `20261124145303`) | 1.80 | 1.80 |
| CloudWatch Logs, custom and vended (flow logs, Postgres) | $0.57 per GB ingested, $0.03 per GB-month stored | about 5 GB: 3.30 | about 20 GB: 12.00 |
| Container Insights metrics | $0.07 per metric-month | about 3.50 | about 4.00 |
| S3, ECR, SES | $0.023 and $0.10 per GB-month; SES per message | about 2.00 | about 3.00 |
| CloudFront | always-free tier: 1 TB and 10 M requests a month | 0 | 0 |
| Malware scanning of the evidence bucket (below) | free tier: 1,000 objects and 1 GB a month | 0 | 0 |
| **Total** | | **about 196** | **about 329** |

**Against the budget alerts.**
- **Dev** alerts at 150, 250 and 400. Its estimate (about 196) now passes the first one.
- **Prod** alerts at 250, 350 and 450 (owner decision, #286). Its estimate (about 329, or about
  355 with db.t4g.small Multi-AZ) passes the first one, and the larger database the second.
- **The operator portal** (#499 to #502) adds about 13 a month to each: its service, three
  secrets, the runner and the alarms. Its distribution shares CloudFront's free tier.
- **What raised them:** the scan egress filter (issue 454) adds about 43 in dev and 86 in prod,
  mostly interface endpoints. Moving the thresholds is the owner's decision.

**What moves the total most:**
- **NAT gateways** are about a fifth to a quarter of it. They stay: Cognito, Microsoft Graph and
  Google APIs need the internet, and the API and the egress proxy reach them through NAT.
- **Interface endpoints** (issue 454) are what lets a scan task run with no route to the
  internet: Fargate pulls the image and ships logs through the task's own interface. Four
  endpoints are the minimum; KMS and STS need none, because S3, Secrets Manager and the
  credentials endpoint call them.
- **The database class.** micro is the code's default; measure before production.
- **Flow log volume.** It is billed at $0.57 per GB. If it grows, keep ALL traffic, but send it
  to S3 instead of CloudWatch.

**Malware scanning** (evidence-malware-scanning spec). Prices from the eu-south-2 Price List
files for GuardDuty (publication 2026-10-30), S3 (2026-11-21), SQS (2026-11-11) and EventBridge
(2026-11-18), read on 2026-11-24:
- **GuardDuty Malware Protection for S3:** each account and Region gets 1,000 objects and 1 GB
  scanned free a month. Beyond that, $0.000242 per object and $0.1005 per GB. Example: 10,000
  objects and 10 GB in a month cost 9,000 × 0.000242 + 9 × 0.1005 = $3.08.
- **What is scanned:** every new object version in the bucket. Uploaded evidence is at most
  25 MB a file; scan outputs are scanned too, a few files per scan (spec D2).
- **Tags:** GuardDuty's result tag is billed at $0.0065 per 10,000 tags a month, and every
  locked object keeps its tag.
- **S3 calls:** the scan role's GET and tagging requests are billed at $0.004 per 10,000 GET
  and $0.0053 per 1,000 PUT.
- **SQS and the KMS key:** one poll a minute is about 43,000 requests a month, inside the free
  million. The queues key is the fifth KMS key above.
- **EventBridge:** S3 events ingested for the managed rule are billed under EventBridge pricing
  (GuardDuty, "Pricing and usage cost for Malware Protection for S3"). The price list shows
  $1.00 per million custom events. Which usage type applies to these events is not confirmed,
  so read it as a candidate. At pilot volume it rounds to 0.
- **Open work, not built:** alarms on the dead-letter queue (`<env>-file-scans-dead`) and on the
  plan's status events. Until they exist, check the queue's depth and the plan's status in the
  GuardDuty console after each deploy.

**Not included:**
- Cognito Essentials, for both pools (free up to its monthly active user allowance; check the
  Cognito pricing page);
- EventBridge Scheduler: about 120 invocations a month (candidate: not in the price files read
  above; check the Scheduler pricing page);
- data transfer to the internet beyond CloudFront's free tier;
- AWS Support plans;
- Route 53, if the domain's DNS is hosted there.

## 10. Scans for a new customer (owner only)

Each customer's scan roles come from OpenTofu, applied by you (owner, 2026-11-24). No Atesta
process can create IAM roles.

1. Find the organization's id (a lowercase UUID) and its connectors: `m365`,
   `google_workspace` or both.
2. Add it to `scan_organizations` in the environment's untracked tfvars:

   ```hcl
   scan_organizations = {
     "00000000-0000-4000-8000-000000000000" = ["m365", "google_workspace"]
   }
   ```

3. Plan and apply. The plan must add only roles named
   `atesta-scan/<env>/{scan-m365,verify-gws,scan-gws}-<org id>` and their inline policies.
4. For Google Workspace, `scanner/runbooks/google_sa.sh` writes the two credential files
   (`docs/runbooks/google-workspace.md`). Store each one as a secret under the secrets key, from
   the file, and delete the files:

   ```bash
   aws secretsmanager create-secret --name "atesta/atesta-dev/google/<org id>" \
     --kms-key-id alias/atesta-dev-secrets --secret-string "file://<store>/google-<org id>.json"
   aws secretsmanager create-secret --name "atesta/atesta-dev/google-verifier/<org id>" \
     --kms-key-id alias/atesta-dev-secrets --secret-string "file://<store>/google-verifier-<org id>.json"
   ```

   Then run `atesta-register-google` with `--credential-ref aws-sm:<first ARN>` and
   `--verifier-credential-ref aws-sm:<second ARN>`. The database accepts only this
   organization's own secret names.
5. Removing a customer is the reverse: delete the entry and apply. The roles go, and the stored
   scans stay under the evidence lock.
