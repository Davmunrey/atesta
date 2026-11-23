# scanner

The scan runner image and its wrapper (scanner-connectors spec, Scanner image and wrapper).

| Path | What |
|---|---|
| `Dockerfile` | Image: base and PowerShell 7.6.10 pinned as Prowler 5.52.0's own image pins them; Prowler and its dependencies hash-locked; no PowerShell modules (PR 10); uid 10001 |
| `requirements.in`, `overrides.txt` → `requirements.txt` | Prowler 5.52.0 and 245 dependencies with hashes, resolved with the 7-day cooldown (Prowler itself exempted by date) |
| `build-requirements.txt` | Hash-locked setuptools for the 12 sdist-only dependencies, built with `--no-build-isolation` |
| `atesta_scanner/` | The wrapper `atesta-scan`: invocation contract and exit codes; the run lands in PR 6 |
| `expected/` | Committed `--list-checks-json` output and the PowerShell-backed list (its README) |
| `tools/powershell_checks.py` | Derives the PowerShell-backed list from Prowler's source |
| `golden.sh` | Offline golden, run in CI on every change |

Regenerate the lock with the command in the header of each `.txt` file, then run the golden.
`overrides.txt` replaces `pymongo==4.15.1`, which `huaweicloudsdkcore` pins and which carries
five known vulnerabilities, with a fixed release; nothing on the M365 or Google path imports it,
so `pip check` reports that one pin conflict on purpose.

```bash
docker build -f scanner/Dockerfile -t atesta-scanner .
scanner/golden.sh atesta-scanner
```
