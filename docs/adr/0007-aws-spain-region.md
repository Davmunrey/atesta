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
