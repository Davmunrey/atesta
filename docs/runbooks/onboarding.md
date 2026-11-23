# Runbook: customer onboarding

- **When:** a new customer signs up for a workspace.
- **Who:** the customer's first user becomes its owner; Atesta supports by email or call.

## Before access

1. **Contract and DPA.** The order form and the data processing agreement are signed (legal review is a human gate; see ROADMAP "Only a human can do").
2. **Region.** The customer is told that data stays in AWS eu-south-2 (ADR-007), with the EU-only exceptions listed in ADR-007 amendment 1.

## In the app

3. **Sign in and create the organization.** The first person signs in and creates the organization; they become its owner.
4. **People and roles** (`docs/specs/rbac.md`):
   - **Administrators** run the self-assessment.
   - **Contributors** assess the measures assigned to them and see them in *Mi trabajo*.
   - **External auditors** get read-only access with an end date, at most one year ahead.
5. **Framework and scope.** The customer opens their framework (ENS first). An administrator defines the scope (category and levels per dimension), and Atesta proposes which measures apply.
6. **Owners and dates.** Assign an owner and a due date to each measure, so *Mi trabajo* and the "overdue" view work.
7. **First review.** After the first pass, the security officer records the review, and the owner exports the statement of applicability (CSV in Spanish or English).

## Check before closing onboarding

- The owner can see *Ajustes* and knows about the export and closure (`offboarding.md`).
- At least one administrator besides the owner exists, so access does not depend on one person.
- The customer knows that Atesta prepares evidence and does not certify compliance (claims-honesty spec).
