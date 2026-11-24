#!/usr/bin/env bash
# Create, rotate or disable one Atesta org's Google service accounts (scanner-connectors spec,
# D7 to D9; docs/runbooks/google-workspace.md; issue 421). The owner runs it; no agent can.
#
#   google_sa.sh create  --project P --org ORG_ID --store DIR --connection CONNECTION_ID
#   google_sa.sh rotate  --project P --org ORG_ID --store DIR
#   google_sa.sh disable --project P --org ORG_ID --store DIR
#
# create: the org's scan and verifier service accounts, one key each, stored in the local
#   credential store DIR as local:google-<org> and local:google-verifier-<org>, then
#   atesta-register-google records both on the connection. Prints the client ids and the exact
#   scope strings the customer authorizes.
# rotate: a new key per account replaces the stored one, then every older key is deleted (D9).
# disable: the disconnect step: every key deleted, both accounts disabled, stored keys removed.
#
# A new key is written only to memory: a RAM disk this script creates and destroys (macOS) or a
# private tmpfs folder (Linux). It is removed on every exit, error or interrupt. Nothing here
# prints a key. Runs with bash 3.2 (macOS). Needs gcloud signed in as the owner, and uv.
#
# Overrides (tests): GCLOUD, ATESTA_REGISTER_GOOGLE, ATESTA_PYTHON, ATESTA_SHM (Linux tmpfs base).

set -euo pipefail
umask 077

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
GCLOUD="${GCLOUD:-gcloud}"
PYTHON="${ATESTA_PYTHON:-uv run --project $REPO python}"
REGISTER="${ATESTA_REGISTER_GOOGLE:-uv run --project $REPO atesta-register-google}"
UUID_RE='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
PROJECT_RE='^[a-z][a-z0-9-]{4,28}[a-z0-9]$'
SCAN_VAR="GOOGLEWORKSPACE_CREDENTIALS_CONTENT"
VERIFIER_VAR="ATESTA_GOOGLE_VERIFIER_CREDENTIALS_CONTENT"

die() { printf 'google_sa.sh: %s\n' "$1" >&2; exit 1; }
usage() {
  printf 'usage: google_sa.sh create|rotate|disable --project P --org ORG_ID --store DIR' >&2
  printf ' [--connection CONNECTION_ID]\n' >&2
  exit 2
}

[ "$#" -ge 1 ] || usage
command="$1"; shift
case "$command" in create|rotate|disable) ;; *) usage ;; esac
project="" org="" store="" connection=""
while [ "$#" -gt 0 ]; do
  [ "$#" -ge 2 ] || usage
  case "$1" in
    --project) project="$2" ;;
    --org) org="$2" ;;
    --store) store="$2" ;;
    --connection) connection="$2" ;;
    *) usage ;;
  esac
  shift 2
done
[[ "$org" =~ $UUID_RE ]] || die "--org must be the organization's UUID"
[[ "$project" =~ $PROJECT_RE ]] || die "--project must be a GCP project id"
if [ "$command" = create ]; then
  [[ "$connection" =~ $UUID_RE ]] || die "create needs --connection, the connection's UUID"
fi

# --- the local credential store (scanning/local.py LocalCredentialStore) -------------------------

[ -d "$store" ] || die "the store $store is not a folder"
store="$(cd "$store" && pwd)"
dir="$store"
while [ "$dir" != "/" ]; do
  [ -e "$dir/.git" ] && die "the store $store is inside a repository: keys never live in one"
  dir="$(dirname "$dir")"
done
mode() { $PYTHON -I -c 'import os,stat,sys; print(stat.S_IMODE(os.stat(sys.argv[1]).st_mode) & 0o077)' "$1"; }
[ "$(mode "$store")" = 0 ] || die "the store $store must be readable by you only (chmod 700)"
SCAN_FILE="$store/google-$org.json"
VERIFIER_FILE="$store/google-verifier-$org.json"

hex="$(printf '%s' "$org" | tr -d '-' | cut -c1-23)"
SCAN_EMAIL="scan-$hex@$project.iam.gserviceaccount.com"
VERIFY_EMAIL="verify-$hex@$project.iam.gserviceaccount.com"

# --- memory for new keys -------------------------------------------------------------------------

KEY_DIR="" RAM_DEVICE=""
cleanup() {
  if [ -n "$KEY_DIR" ] && [ -d "$KEY_DIR" ]; then
    find "$KEY_DIR" -type f -exec rm -f {} + 2>/dev/null || true
  fi
  if [ -n "$RAM_DEVICE" ]; then
    hdiutil detach "$RAM_DEVICE" -force >/dev/null 2>&1 || true
  elif [ -n "$KEY_DIR" ]; then
    rmdir "$KEY_DIR" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

memory() {
  case "$(uname -s)" in
    Darwin)  # a RAM disk, destroyed in cleanup (candidate until the owner's first run)
      RAM_DEVICE="$(hdiutil attach -nomount ram://16384 | awk '{print $1}')"
      [ -n "$RAM_DEVICE" ] || die "could not create a RAM disk for the keys"
      diskutil erasevolume HFS+ "atesta-keys-$$" "$RAM_DEVICE" >/dev/null
      KEY_DIR="/Volumes/atesta-keys-$$"
      touch "$KEY_DIR/.metadata_never_index"  # no Spotlight copy of a key
      ;;
    Linux)
      local base="${ATESTA_SHM:-/dev/shm}"
      local kind
      kind="$(stat -f -c %T "$base" 2>/dev/null || true)"
      case "$kind" in tmpfs|ramfs) ;; *) die "$base is not memory (tmpfs): new keys never touch a disk" ;; esac
      KEY_DIR="$(mktemp -d "$base/atesta-keys.XXXXXX")"
      ;;
    *) die "run this on macOS or Linux" ;;
  esac
  chmod 700 "$KEY_DIR"
}

# --- gcloud steps (Google Cloud IAM docs, read 2026-11-24) ---------------------------------------

exists() {
  [ -n "$("$GCLOUD" iam service-accounts list --project "$project" \
    --filter "email=$1" --format 'value(email)')" ]
}

ensure_account() {  # name, label
  local email="$1@$project.iam.gserviceaccount.com"
  if ! exists "$email"; then
    "$GCLOUD" iam service-accounts create "$1" --project "$project" \
      --display-name "Atesta $2 $org" \
      --description "Atesta $2 service account for organization $org (read-only, D7)" >/dev/null
  fi
}

ids() {  # email -> "uniqueId oauth2ClientId", both numeric
  local out unique client
  out="$("$GCLOUD" iam service-accounts describe "$1" --project "$project" \
    --format 'value(uniqueId,oauth2ClientId)')"
  read -r unique client <<<"$out" || true
  [[ "$unique" =~ ^[0-9]{6,30}$ && "$client" =~ ^[0-9]{6,30}$ ]] \
    || die "gcloud returned no numeric ids for $1"
  printf '%s %s\n' "$unique" "$client"
}

new_key() {  # email, file in KEY_DIR
  "$GCLOUD" iam service-accounts keys create "$2" --iam-account "$1" --project "$project" \
    >/dev/null 2>&1 || die "gcloud could not create a key for $1 (is the project exempt from the key-creation block?)"
}

# Store {variable: key JSON} with mode 0600; prints the new key's id. Never prints the key.
store_key() {  # variable, key file, destination
  $PYTHON -I - "$1" "$2" "$3" <<'PY'
import json, os, sys
variable, source, destination = sys.argv[1:]
with open(source) as handle:
    key = json.load(handle)
if key.get("type") != "service_account" or not key.get("private_key_id"):
    sys.exit("google_sa.sh: gcloud did not write a service account key")
temporary = destination + ".tmp"
descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w") as handle:
    json.dump({variable: json.dumps(key)}, handle)
os.replace(temporary, destination)
print(key["private_key_id"])
PY
}

delete_keys() {  # email, key id to keep ("" deletes every user-managed key)
  local key
  for key in $("$GCLOUD" iam service-accounts keys list --iam-account "$1" --project "$project" \
      --managed-by user --format 'value(name.basename())'); do
    [ "$key" = "$2" ] && continue
    "$GCLOUD" iam service-accounts keys delete "$key" --iam-account "$1" --project "$project" \
      --quiet >/dev/null
  done
}

scopes() {  # the expected scopes of one client, from the allowlist (atesta_core, rule 1)
  $PYTHON -c "from atesta_core.connectors.readonly import GOOGLE_V1 as v; \
print(','.join(sorted(v.$1)))"
}

# --- commands ------------------------------------------------------------------------------------

case "$command" in
  create)
    [ -e "$SCAN_FILE" ] || [ -e "$VERIFIER_FILE" ] \
      && die "this org already has stored keys: use rotate, or disable first"
    memory
    ensure_account "scan-$hex" scan
    ensure_account "verify-$hex" verifier
    scan_ids="$(ids "$SCAN_EMAIL")"
    verify_ids="$(ids "$VERIFY_EMAIL")"
    read -r scan_unique scan_client <<<"$scan_ids"
    read -r verify_unique verify_client <<<"$verify_ids"
    new_key "$SCAN_EMAIL" "$KEY_DIR/scan.json"
    new_key "$VERIFY_EMAIL" "$KEY_DIR/verify.json"
    scan_key="$(store_key "$SCAN_VAR" "$KEY_DIR/scan.json" "$SCAN_FILE")"
    verify_key="$(store_key "$VERIFIER_VAR" "$KEY_DIR/verify.json" "$VERIFIER_FILE")"
    rm -f "$KEY_DIR/scan.json" "$KEY_DIR/verify.json"
    # A key left by an earlier run that failed halfway never stays usable.
    delete_keys "$SCAN_EMAIL" "$scan_key"
    delete_keys "$VERIFY_EMAIL" "$verify_key"
    $REGISTER --organization-id "$org" --connection-id "$connection" \
      --client-id "$scan_client" --verifier-client-id "$verify_client" \
      --unique-id "$scan_unique" --verifier-unique-id "$verify_unique" \
      --credential-ref "local:google-$org" --verifier-credential-ref "local:google-verifier-$org"
    printf '\nSend the customer these two domain-wide delegation entries (Admin console,\n'
    printf 'Security, Access and data control, API controls, Manage Domain Wide Delegation):\n\n'
    printf 'Client ID %s\nScopes %s\n\n' "$scan_client" "$(scopes scan_scopes)"
    printf 'Client ID %s\nScopes %s\n' "$verify_client" "$(scopes verifier_scopes)"
    ;;
  rotate)
    [ -e "$SCAN_FILE" ] && [ -e "$VERIFIER_FILE" ] || die "this org has no stored keys to rotate"
    memory
    new_key "$SCAN_EMAIL" "$KEY_DIR/scan.json"
    new_key "$VERIFY_EMAIL" "$KEY_DIR/verify.json"
    scan_key="$(store_key "$SCAN_VAR" "$KEY_DIR/scan.json" "$SCAN_FILE")"
    verify_key="$(store_key "$VERIFIER_VAR" "$KEY_DIR/verify.json" "$VERIFIER_FILE")"
    rm -f "$KEY_DIR/scan.json" "$KEY_DIR/verify.json"
    delete_keys "$SCAN_EMAIL" "$scan_key"
    delete_keys "$VERIFY_EMAIL" "$verify_key"
    printf 'Rotated both keys of organization %s.\n' "$org"
    ;;
  disable)
    for email in "$SCAN_EMAIL" "$VERIFY_EMAIL"; do
      if exists "$email"; then
        delete_keys "$email" ""
        "$GCLOUD" iam service-accounts disable "$email" --project "$project" >/dev/null
      fi
    done
    rm -f "$SCAN_FILE" "$VERIFIER_FILE"
    printf 'Disabled both service accounts of organization %s and deleted their keys.\n' "$org"
    ;;
esac
