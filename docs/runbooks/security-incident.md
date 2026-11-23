# Runbook: security incident at Atesta

- **When:** a suspected or confirmed security event in Atesta's own systems or code. Examples:
  - cross-tenant access;
  - a leaked credential or token;
  - an unexpected write capability in a connector;
  - customer data processed outside the EU;
  - a vulnerability report through the channel in `SECURITY.md`.
- **Who:** the owner leads until an on-call rotation exists. Keep one timeline in a private incident ticket. Never put customer content or secrets in it (CLAUDE.md rule 2).

## 1. Triage (first hour)

- **Classify:**
  - **Critical:** cross-tenant read or write, credential exposure, write access to a customer system.
  - **High:** a confirmed vulnerability without evidence of use.
  - **Low:** everything else.
- **Decide whether personal data may be affected.** If it may, it is a potential personal data breach and step 4 applies from now.

## 2. Contain

- **Revoke or rotate** the affected credentials and sessions.
- **Disable** the affected connector or feature.
- **Block** the path. For cross-tenant suspicion, stop the API rather than leave it running.
- **Keep the evidence:** logs, the commit and the request ids. Do not delete or edit.

## 3. Fix and verify

- Fix through a pull request with a failing test first (AGENTS.md rules), merged with green CI.
- Show the fix with the test name and the CI run, as the verification rules in CLAUDE.md require.

## 4. Notify

- **Customers.** For a personal data breach Atesta is the processor. Under GDPR art. 33(2), it notifies each affected customer (the controller) without undue delay after becoming aware of it.
  - The message gives what is known, the data and customers concerned, the likely consequences, and the measures taken (the content listed in art. 33(3)), in phases if needed (art. 33(4)).
  - The customer decides on its own notification to the authority and to data subjects (art. 33 and 34). Their own obligations, such as NIS2 or ENS reporting, are theirs; give them what they need.
- **Reporter.** Tell the reporter of a vulnerability report the outcome, without details of other customers.
- **Atesta's own obligations.** Whether Atesta itself must report to an authority, under NIS2 or other law, is checked with legal advice for each incident. Do not assume it either way.

## 5. Close

- Write a post-incident review: timeline, cause, what worked, and follow-up issues with owners.
- Record every personal data breach and its handling in the incident register, even when nobody had to be notified.
- If the cause was a missing test, add the test before closing.
