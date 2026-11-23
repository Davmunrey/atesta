#!/usr/bin/env bash
# Offline golden for the scanner image (scanner-connectors spec, Golden tests). No network and
# no credentials. The image must print exactly the committed check lists, re-derive the
# PowerShell-backed list, run pwsh 7.6.10 as uid 10001 on a read-only root filesystem, and
# carry no MSAL.PS. Usage: scanner/golden.sh <image>
set -euo pipefail

image=$1
version=5.52.0
expected=scanner/expected/$version
out=$(mktemp -d)

run() {
  docker run --rm --network none --read-only --user 10001 --cap-drop ALL \
    --security-opt no-new-privileges \
    --tmpfs /work:mode=1777 --tmpfs /home/scanner:mode=1777 "$@"
}

for provider in m365 googleworkspace; do
  run --entrypoint prowler "$image" "$provider" --list-checks-json >"$out/$provider.json"
  cmp "$expected/$provider.json" "$out/$provider.json"
done

run -v "$PWD/scanner/tools:/tools:ro" --entrypoint python "$image" -I /tools/powershell_checks.py \
  /usr/local/lib/python3.13/site-packages/prowler/providers/m365/services \
  "/opt/atesta/expected/$version/m365.json" >"$out/m365-powershell.json"
cmp "$expected/m365-powershell.json" "$out/m365-powershell.json"

test "$(run --entrypoint id "$image" -u)" = 10001
test "$(run --entrypoint pwsh "$image" -NoProfile -NonInteractive \
  -Command '$PSVersionTable.PSVersion.ToString()')" = 7.6.10
run --entrypoint pwsh "$image" -NoProfile -NonInteractive \
  -Command 'if (Get-Module -ListAvailable -Name MSAL.PS) { exit 1 }'
run --entrypoint python "$image" -c 'import atesta_core.exclusions, atesta_scanner.run'

echo "offline golden: ok ($image)"
