# Runbook: operator portal staff accounts

- **When:** the first admin of an environment, a new colleague, a role change, a lost device, or
  a colleague who leaves.
- **Spec:** `docs/specs/operator-portal.md` (build step 7). ADR-017, "Staff identity".
- **Who:** the owner, with AWS access to the environment, creates and removes accounts in the
  staff pool. Admins manage roles in the portal (*Administración → Equipo*).

A staff member needs two things: an account in the staff Cognito pool (`atesta-<env>-staff`),
and an enabled row in `operator_staff` with that account's `sub` and a role (`admin`, `billing`
or `support`). The account proves who they are; the row says what they may do. Without the row,
the portal answers "Sin acceso al portal" ("No access to the portal").

## Running a staff command in AWS

The command `atesta_api.ops.staff` is in the API image. It runs with the migration credential, as
a one-off task of the erasure task definition, which holds that credential. Fill in the values
from `tofu output -json deploy`:

```bash
run_ops() {  # usage: run_ops <args of atesta_api.ops.staff or atesta_api.ops.erase>
  module=$1; shift
  overrides=$(jq -cn --arg m "$module" '{containerOverrides: [{name: "erasure",
    command: (["python", "-m", $m] + $ARGS.positional)}]}' --args -- "$@")
  aws ecs run-task --cluster <deploy.cluster> --launch-type FARGATE \
    --task-definition <deploy.erasure_family> \
    --network-configuration "awsvpcConfiguration={subnets=[<deploy.private_subnets>],securityGroups=[<deploy.app_security_group>],assignPublicIp=DISABLED}" \
    --overrides "$overrides" --query 'tasks[0].taskArn' --output text
}
```

The output is in the log group `/atesta/<env>/erasure`, stream prefix `erasure`. Each command
prints one JSON line, or `refused: …` and exit code 2 when it changed nothing. Every change is in
the portal's *Registro de operaciones*, with the admin you name in `--by` and your reason.

## 1. The first admin (once per environment)

1. **Create the account.** The pool emails a temporary password, valid for 3 days. Keep the
   `sub` it prints:

   ```bash
   aws cognito-idp admin-create-user --user-pool-id <staff_cognito.user_pool_id> \
     --username <your email> --desired-delivery-mediums EMAIL \
     --user-attributes Name=email,Value=<your email> Name=email_verified,Value=true \
     --query 'User.Attributes[?Name==`sub`].Value' --output text
   ```

2. **Add yourself as admin.** `--first` is accepted only while no admin is enabled; the trail
   names you as the one who acted:

   ```bash
   run_ops atesta_api.ops.staff add --email <your email> --sub <sub> --role admin --first \
     --reason "First admin, <ticket>"
   ```

3. **Sign in** at `https://admin.<domain>` (step 3 below).
4. **Second admin.** Add a second admin as soon as you can (section 2). An erasure then needs
   two people. With one admin, the same admin approves only after 72 hours (spec, owner answer 3).

## 2. Adding a colleague

1. Agree on the role, the least that does the job:
   - **support:** reads metadata;
   - **billing:** also sets plans and billing details;
   - **admin:** everything, including staff and destructive actions.
2. Create the account (section 1, step 1, with their email).
3. Add the row, naming yourself as the acting admin:

   ```bash
   run_ops atesta_api.ops.staff add --email <their email> --sub <sub> --role support \
     --by <your admin email> --reason "Joined support, <ticket>"
   ```

4. **Changing a role later:** *Equipo → Gestionar → Cambiar el rol*. Nobody can change their own
   row. The last enabled admin cannot be demoted.

## 3. Signing in and MFA enrolment

1. The colleague opens `https://admin.<domain>` and chooses *Iniciar sesión*.
2. **First sign-in:** the email and the temporary password, then a new password (12 characters
   or more).
3. **Authenticator app (TOTP):** MFA is required in the staff pool. At the first sign-in,
   Cognito asks for an authenticator app (scan the QR code, type a code). Every later sign-in asks
   for a code. SMS and email codes are never offered.
4. **Passkeys:** offered only once the environment has passkeys on (deploy runbook, "Operator
   portal checks", step 4). Then managed login offers sign-in with a passkey that verifies the
   person (fingerprint, face or device PIN). Password plus authenticator app stays the fallback.
   **Candidate:** how managed login offers to register a passkey has not been seen on the real
   pool yet; check it with the first admin and update this step.

## 4. A lost device or password

The pool has no self-service recovery (`admin_only`): a mailbox alone never resets a staff
account.

1. Check who is asking, by a channel other than the email: a call, or in person.
2. **Candidate, not yet tried on the real pool:**
   - **Lost password:** set a temporary password and give it to them by that other channel.
     The next sign-in asks for a new one:
     ```bash
     aws cognito-idp admin-set-user-password --user-pool-id <pool> --username <email> \
       --password "<temporary>" --no-permanent
     ```
   - **Lost authenticator:** clear the TOTP preference so the next sign-in enrols a new one:
     ```bash
     aws cognito-idp admin-set-user-mfa-preference --user-pool-id <pool> --username <email> \
       --software-token-mfa-settings Enabled=false,PreferredMfa=false
     ```
   - If either does not behave as described, disable and delete the account (section 5) and
     add them again with a new account. A new account has a new `sub`, so its row is new too.
3. Note the request and what you did in the ticket.

## 5. A colleague who leaves (offboarding staff)

Do it on their last day, in this order:

1. **Portal access:** *Equipo → Gestionar → Desactivar el acceso*, with the reason. If the
   portal is not available, use the command instead:

   ```bash
   run_ops atesta_api.ops.staff disable --email <their email> --by <your admin email> \
     --reason "Left the team, <ticket>"
   ```

   The operator API refuses a staff token without an enabled row at once (403).
2. **The account:** disable it and end its sessions. `AdminDisableUser` "revokes all access
   tokens for the user" (Cognito API reference). The global sign-out also revokes the refresh
   tokens:

   ```bash
   aws cognito-idp admin-disable-user --user-pool-id <pool> --username <their email>
   aws cognito-idp admin-user-global-sign-out --user-pool-id <pool> --username <their email>
   ```

3. **Keep the row, disabled.** The operator trail references it, so it is never deleted. Delete
   the Cognito account after the period your records policy sets, if at all.
4. **An admin who leaves:** if they were one of two admins, add another admin first (section 2),
   so an erasure still needs two people.

## 6. Re-enabling a colleague

Re-enable the account (`aws cognito-idp admin-enable-user …`), then *Equipo → Gestionar →
Reactivar el acceso*, or `run_ops atesta_api.ops.staff enable …`.
