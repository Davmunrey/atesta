# Expected check lists

`<version>/<provider>.json` is the unmodified output of `prowler <provider> --list-checks-json`
for the pinned engine (scanner-connectors spec, Image). Ingest reads it as the expected set; the
image build (PR 5) fails if the image prints anything else.

| File | Checks | sha256 |
|---|---|---|
| `5.49.0/m365.json` | 149 | `29ce7728f3c31aa1e16cada80d906fa5199b865c4a564708b5d5454951ffb3f7` |
| `5.49.0/googleworkspace.json` | 65 | `b245453bf8a86a4c220a552631d29c7eb2e0253ebd2524f1609f408d4e94e168` |

Generated offline, with no credentials, from the wheel `prowler-5.49.0-py3-none-any.whl`
(sha256 `e5ed983eb3faf34a72cb0f1460e98516dd5f36ce4db443f886e0d60a205be705`, as in the spec),
installed in a throwaway virtual environment:

```bash
prowler m365 --list-checks-json > m365.json
prowler googleworkspace --list-checks-json > googleworkspace.json
```

`5.49.0/m365-powershell.json` (54 checks; sha256
`b985df5e0982fa768b606fbf4d139b212070236d5a4f0f6a16a8cbb5644c7105`) lists the M365 checks that
read PowerShell data, excluded as `not_granted` until PR 10 (D1). It is the output of
`scanner/tools/powershell_checks.py` over the same wheel's `prowler/providers/m365/services`:
a check counts when it reads, through `<service>_client`, an attribute its service fills only
inside `if self.powershell:`. Per service: Exchange 17, Defender 17, Teams 16, Admin center 3,
Purview 1, as the spec states; no Entra check (Entra prefers Graph `accountEnabled`).

```bash
python -I scanner/tools/powershell_checks.py \
  <venv>/lib/python3.12/site-packages/prowler/providers/m365/services \
  scanner/expected/5.49.0/m365.json > m365-powershell.json
```

Exclusions with their reasons (D1 and D3 `not_granted`, D6 `excluded`) are composed by
`atesta_core.exclusions`.
