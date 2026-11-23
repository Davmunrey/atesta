# ADR-007: AWS Spain region only

- Status: accepted (2026-11-12)

## Decision
All customer data stored and processed in AWS eu-south-2, using services within AWS's ENS High
certification scope (verify per service).

## Consequences
Data residency is a sales argument for public-sector suppliers. Fewer managed services than in
larger regions; check availability before adopting any new service.

## Amendment 1 (accepted 2026-11-13): EU residency boundary
Atesta will sell outside Spain, so the residency boundary is the EU, not Spain. eu-south-2 stays
the primary region for every data store and all compute. A managed service may process customer
data in another EU region only when eu-south-2 cannot serve it; each case is listed here and in
the DPA sub-processor list. No processing outside the EU. The ENS scope check per service still
applies.

| Service | Region | Data | Why |
|---|---|---|---|
| Cognito email via SES | eu-west-3 (Paris) | User email addresses, verification and reset codes | A user pool in eu-south-2 cannot use SES in its own region (AWS Cognito email Region table, checked in the 2026-11-13 review) |

## Amendment 2 (accepted by the owner 2026-11-23): CloudFront in front of the app
The web app is a static export served by CloudFront, and it is single-origin: CSP
`connect-src 'self'` and a same-site session cookie. So `/api/*` and `/auth/*` reach the
eu-south-2 load balancer through the same distribution (hosted-environment spec, PR #254).
CloudFront's edge locations are not all in the EU: PriceClass_100 covers Europe and North
America, and no price class is EU-only. Requests are routed to the nearest edge, so a user
outside Europe goes through an edge outside the EU. The owner accepted this as an exception to
amendment 1's "no processing outside the EU", under these conditions:

| Condition | How it holds |
|---|---|
| Transit only, nothing stored at the edge | `/api/*` and `/auth/*` use the managed CachingDisabled policy. The static site holds no customer data. CloudFront standard logs are not enabled; the load balancer's access logs stay in eu-south-2 |
| Encrypted end to end | Viewer TLS 1.2+ (TLSv1.2_2021); origin HTTPS only, TLS 1.2+; the load balancer accepts only CloudFront's origin-facing prefix list |
| ENS High scope | CloudFront is in AWS's ENS High scope, except Embedded PoPs, which Atesta does not use (services-in-scope page, updated 2025-11-06, read 2026-11-23) |
| Listed for customers | docs/legal/subprocessors.md names CloudFront and what passes through it. The transfer terms come from the AWS GDPR DPA, to confirm when the account exists |

Revisit this if a customer contract requires EU-only transit. The alternative then is an API
hostname served directly from eu-south-2, with app changes: CSP `connect-src`, cookie scope and
CORS.

| Service | Region | Data | Why |
|---|---|---|---|
| CloudFront (edge for the app and its API) | Global edge locations (PriceClass_100: Europe and North America) | In transit only: requests and responses of signed-in members, including session cookies and request bodies; nothing cached for `/api` and `/auth` | The single-origin web app needs one hostname for the site and the API |
