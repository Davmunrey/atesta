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
- the registries, Cognito, the GitHub roles and the budget alerts.

It creates no ECS service and no CloudFront yet: `images` and `edge` are still unset. Note the
outputs `deploy.repositories` and `github_oidc` (the plan and apply role ARNs).

In prod, also pass these. The Cognito email identity is created in eu-west-3, and
`platform.cognito_dns` lists its DNS records.

```bash
-var app_url=https://app.<domain>
-var cognito_mail_domain=<domain>
-var cognito_from="Atesta <no-reply@<domain>>"
```

## 3. Domain, certificates and DNS

1. Request two ACM certificates, with DNS validation:
   - **CloudFront:** in **us-east-1**, for `app.<domain>`. It is a certificate only; no customer
     data goes there.
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
   - `api-origin.<domain>`: alias to the load balancer (output `platform.api_load_balancer`).

## 4. Secrets (never in git, never in shell history)

Generate two passwords and write the connection URLs. Work in a tmpfs or with `umask 077`, and
delete the files afterwards:

```bash
host=$(tofu output -json platform | jq -r .database_endpoint)
for role in app migration; do
  user=$([ $role = app ] && echo atesta_app || echo atesta_owner)
  pass=$(aws secretsmanager get-random-password --exclude-punctuation --password-length 40 --query RandomPassword --output text)
  printf 'postgresql+psycopg://%s:%s@%s:5432/atesta' "$user" "$pass" "$host" > "/dev/shm/$role-url"
  aws secretsmanager put-secret-value --secret-id "atesta/atesta-dev/db/$role-url" --secret-string "file:///dev/shm/$role-url"
  rm "/dev/shm/$role-url"
done
head -c 32 /dev/urandom | base64 > /dev/shm/session-key
aws secretsmanager put-secret-value --secret-id atesta/atesta-dev/api/session-key --secret-string file:///dev/shm/session-key
rm /dev/shm/session-key
```

On macOS, use a directory created with `mktemp -d` instead of `/dev/shm`, and remove it
afterwards.

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
           "web_certificate_arn": "<us-east-1 certificate ARN>",
           "api_origin_domain": "api-origin.<domain>",
           "api_certificate_arn": "<eu-south-2 certificate ARN>",
           "content_security_policy": "filled in by the workflow"
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

       Prod also adds `app_url`, `cognito_mail_domain` and `cognito_from`.
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
   `bootstrap done; LOGIN set for atesta_app, atesta_owner`.
3. Run the deploy workflow again. This time the migrations and the smoke check pass.
4. Point DNS (step 3.4), sign up at `https://app.<domain>` with MFA, and walk the pilot guide's
   first steps.

## 7. Every later deploy

Merge to `main`, then run the deploy workflow for the environment. The reviewers you set in
step 5 approve each run.

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
| RDS PostgreSQL db.t4g.micro | $0.018 per hour Single-AZ, $0.035 Multi-AZ | 13.14 | 25.55 |
| RDS gp3 storage, 20 GB | $0.127 per GB-month, $0.254 Multi-AZ | 2.54 | 5.08 |
| RDS backups beyond the database size | $0.095 per GB-month | 0 | about 10 GB: 0.95 |
| NAT gateway | $0.048 per hour plus $0.048 per GB | 1 gateway, 20 GB: 36.00 | 2 gateways, 50 GB: 72.48 |
| Public IPv4 addresses (NAT, load balancer) | $0.005 per hour each | 3: 10.95 | 4: 14.60 |
| Application Load Balancer | $0.0252 per hour plus $0.008 per LCU-hour | about 0.5 LCU: 21.32 | about 1 LCU: 24.24 |
| KMS keys | $1 per key-month (more after rotations) | 5: 5.00 | 5: 5.00 |
| Secrets Manager | $0.40 per secret-month | 4: 1.60 | 9 (with connectors): 3.60 |
| CloudWatch Logs, custom and vended (flow logs, Postgres) | $0.57 per GB ingested, $0.03 per GB-month stored | about 5 GB: 3.30 | about 20 GB: 12.00 |
| Container Insights metrics | $0.07 per metric-month | about 3.50 | about 4.00 |
| S3, ECR, SES | $0.023 and $0.10 per GB-month; SES per message | about 2.00 | about 3.00 |
| CloudFront | always-free tier: 1 TB and 10 M requests a month | 0 | 0 |
| Malware scanning of the evidence bucket (below) | free tier: 1,000 objects and 1 GB a month | 0 | 0 |
| **Total** | | **about 139** | **about 229** |

**Against the budget alerts.** Dev alerts at 150, 250 and 400, and its estimate (about 139)
sits just under the first one. Prod alerts at 250, 350 and 450 (owner decision, #286), so the
estimate (about 229, or about 255 with db.t4g.small Multi-AZ) raises at most the first alert.

**What moves the total most:**
- **NAT gateways** are about a quarter to a third of it. They stay: Cognito, Microsoft Graph and
  Google APIs need the internet, and interface endpoints for ECR, Logs, Secrets Manager, KMS and
  STS would cost more than one NAT gateway: about 6 endpoints × 2 zones × $0.011 an hour = $96.
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
- Cognito Essentials (free up to its monthly active user allowance; check the Cognito pricing
  page);
- data transfer to the internet beyond CloudFront's free tier;
- AWS Support plans;
- Route 53, if the domain's DNS is hosted there.
