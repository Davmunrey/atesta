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

`m365-powershell.json` (the 54 PowerShell-backed checks, excluded until PR 10) arrives with
PR 5.
