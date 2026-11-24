"""The owner's Google service account runbook (scanner-connectors spec, D7 to D9; issue 421).

`scanner/runbooks/google_sa.sh` runs here against a fake `gcloud` that keeps its service accounts
and keys in a state file, and a fake register command that records its arguments. A new key may
only ever sit in memory (tmpfs on Linux), and no key file may survive any exit.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from atesta_core.connectors.readonly import GOOGLE_V1

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scanner" / "runbooks" / "google_sa.sh"
ORG = "aaaaaaaa-0000-4000-8000-000000000001"
CONNECTION = "cccccccc-0000-4000-8000-000000000003"
PROJECT = "atesta-dev-scanners"
HEX = ORG.replace("-", "")[:23]  # service account ids hold 6 to 30 characters
SCAN_EMAIL = f"scan-{HEX}@{PROJECT}.iam.gserviceaccount.com"
VERIFY_EMAIL = f"verify-{HEX}@{PROJECT}.iam.gserviceaccount.com"
IDS = {  # (uniqueId, oauth2ClientId): different on purpose, the verifier matches both
    SCAN_EMAIL: ("333333333333333333333", "111111111111111111111"),
    VERIFY_EMAIL: ("444444444444444444444", "222222222222222222222"),
}
FAKE_GCLOUD = """#!{python}
import json, os, sys
state_path, log = os.environ["FAKE_STATE"], os.environ["FAKE_LOG"]
state = json.load(open(state_path)) if os.path.exists(state_path) else {{"accounts": {{}}}}
args = sys.argv[1:]
with open(log, "a") as handle:
    handle.write(json.dumps({{"tool": "gcloud", "argv": args}}) + "\\n")
def opt(name):
    for a in args:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return args[args.index(name) + 1] if name in args else None
ids = json.loads(os.environ["FAKE_IDS"])
cmd = args[:3]
accounts = state["accounts"]
if cmd == ["iam", "service-accounts", "list"]:
    email = opt("--filter").split("=", 1)[1]
    if email in accounts:
        print(email)
elif cmd == ["iam", "service-accounts", "create"]:
    email = args[3] + "@" + opt("--project") + ".iam.gserviceaccount.com"
    accounts[email] = {{"keys": [], "disabled": False}}
elif cmd == ["iam", "service-accounts", "describe"]:
    print("\\t".join(ids[args[3]]))
elif args[:4] == ["iam", "service-accounts", "keys", "create"]:
    email = opt("--iam-account")
    if os.environ.get("FAKE_FAIL_KEY") == email:
        sys.exit("ERROR: (gcloud) FAILED_PRECONDITION: key creation is not allowed")
    made = sum(len(a["keys"]) for a in accounts.values()) + len(state.get("deleted", []))
    key_id = "k%02d" % (made + 1)
    accounts[email]["keys"].append(key_id)
    key = {{"type": "service_account", "private_key_id": key_id, "client_email": email,
           "client_id": ids[email][1], "private_key": "-----BEGIN PRIVATE KEY-----\\nFAKE\\n"}}
    with open(args[4], "w") as out:
        json.dump(key, out)
elif args[:4] == ["iam", "service-accounts", "keys", "list"]:
    for key_id in accounts[opt("--iam-account")]["keys"]:
        print(key_id)
elif args[:4] == ["iam", "service-accounts", "keys", "delete"]:
    accounts[opt("--iam-account")]["keys"].remove(args[4])
    state.setdefault("deleted", []).append(args[4])
elif cmd == ["iam", "service-accounts", "disable"]:
    accounts[args[3]]["disabled"] = True
else:
    sys.exit("unexpected gcloud call: " + " ".join(args))
json.dump(state, open(state_path, "w"))
"""
FAKE_REGISTER = """#!{python}
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as handle:
    handle.write(json.dumps({{"tool": "register", "argv": sys.argv[1:]}}) + "\\n")
"""


@pytest.fixture
def shm() -> Iterator[Path]:
    """A private folder on the machine's tmpfs: the only place a new key may be written."""
    base = Path("/dev/shm")  # noqa: S108 - the point of the test: keys only in memory
    if not base.is_dir():
        pytest.skip("no /dev/shm on this machine")
    made = Path(tempfile.mkdtemp(prefix="atesta-test.", dir=base))
    yield made
    shutil.rmtree(made, ignore_errors=True)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    made = tmp_path / "secrets"
    made.mkdir(mode=0o700)
    return made


def fakes(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("gcloud", FAKE_GCLOUD), ("register", FAKE_REGISTER)):
        path = bin_dir / name
        path.write_text(body.format(python=sys.executable))
        path.chmod(0o755)
    return {
        "GCLOUD": str(bin_dir / "gcloud"),
        "ATESTA_REGISTER_GOOGLE": str(bin_dir / "register"),
        "ATESTA_PYTHON": sys.executable,
        "FAKE_STATE": str(tmp_path / "state.json"),
        "FAKE_LOG": str(tmp_path / "calls.jsonl"),
        "FAKE_IDS": json.dumps({k: list(v) for k, v in IDS.items()}),
    }


def run(
    tmp_path: Path, shm: Path, store: Path, command: str, *extra: str, **env: str
) -> subprocess.CompletedProcess[str]:
    argv = [
        "bash",  # from PATH, as the owner runs it
        str(SCRIPT),
        command,
        *("--project", PROJECT, "--org", ORG, "--store", str(store)),
        *extra,
    ]
    full_env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "ATESTA_SHM": str(shm),
        **fakes(tmp_path),
        **env,
    }
    return subprocess.run(  # noqa: S603 - fixed argv: bash, the repository's script, test values
        argv, env=full_env, capture_output=True, text=True, timeout=60, check=False
    )


def calls(tmp_path: Path, tool: str) -> list[list[str]]:
    path = tmp_path / "calls.jsonl"
    if not path.exists():
        return []
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    return [c["argv"] for c in lines if c["tool"] == tool]


def state(tmp_path: Path) -> dict[str, object]:
    return dict(json.loads((tmp_path / "state.json").read_text()))


def leftovers(shm: Path) -> list[Path]:
    return [p for p in shm.rglob("*") if p.is_file()]


def stored(store: Path, name: str) -> dict[str, str]:
    path = store / f"{name}-{ORG}.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    return dict(json.loads(path.read_text()))


def create(tmp_path: Path, shm: Path, store: Path) -> subprocess.CompletedProcess[str]:
    return run(tmp_path, shm, store, "create", "--connection", CONNECTION)


def test_create_makes_both_accounts_stores_each_key_and_registers_them(
    tmp_path: Path, shm: Path, store: Path
) -> None:
    done = create(tmp_path, shm, store)
    assert done.returncode == 0, done.stderr
    scan = json.loads(stored(store, "google")["GOOGLEWORKSPACE_CREDENTIALS_CONTENT"])
    verifier = json.loads(
        stored(store, "google-verifier")["ATESTA_GOOGLE_VERIFIER_CREDENTIALS_CONTENT"]
    )
    assert (scan["client_email"], verifier["client_email"]) == (SCAN_EMAIL, VERIFY_EMAIL)
    assert sorted(p.name for p in store.iterdir()) == [
        f"google-{ORG}.json",
        f"google-verifier-{ORG}.json",
    ]
    [register] = calls(tmp_path, "register")
    assert register == [
        *("--organization-id", ORG, "--connection-id", CONNECTION),
        *("--client-id", "111111111111111111111", "--verifier-client-id", "222222222222222222222"),
        *("--unique-id", "333333333333333333333", "--verifier-unique-id", "444444444444444444444"),
        *("--credential-ref", f"local:google-{ORG}"),
        *("--verifier-credential-ref", f"local:google-verifier-{ORG}"),
    ]
    # Each new key was written to the tmpfs folder only, and nothing is left there.
    keys_create = ["iam", "service-accounts", "keys", "create"]
    targets = [c[4] for c in calls(tmp_path, "gcloud") if c[:4] == keys_create]
    assert len(targets) == 2 and all(t.startswith(str(shm) + "/") for t in targets)
    assert leftovers(shm) == []
    # What the owner sends the customer: client ids and exact scope strings, never a key.
    assert "111111111111111111111" in done.stdout and "222222222222222222222" in done.stdout
    assert ",".join(sorted(GOOGLE_V1.scan_scopes)) in done.stdout
    assert ",".join(sorted(GOOGLE_V1.verifier_scopes)) in done.stdout
    assert "PRIVATE KEY" not in done.stdout + done.stderr


def test_create_never_runs_twice_for_an_org(tmp_path: Path, shm: Path, store: Path) -> None:
    assert create(tmp_path, shm, store).returncode == 0
    again = create(tmp_path, shm, store)
    assert again.returncode != 0 and "rotate" in again.stderr
    assert len(calls(tmp_path, "register")) == 1


def test_rotate_stores_a_new_key_then_deletes_every_older_one(
    tmp_path: Path, shm: Path, store: Path
) -> None:
    assert create(tmp_path, shm, store).returncode == 0
    before = stored(store, "google")
    done = run(tmp_path, shm, store, "rotate")
    assert done.returncode == 0, done.stderr
    after = stored(store, "google")
    assert after != before
    accounts = state(tmp_path)["accounts"]
    assert isinstance(accounts, dict)
    new_id = json.loads(after["GOOGLEWORKSPACE_CREDENTIALS_CONTENT"])["private_key_id"]
    assert accounts[SCAN_EMAIL]["keys"] == [new_id]  # D9: one live key per account
    assert len(accounts[VERIFY_EMAIL]["keys"]) == 1
    assert leftovers(shm) == []
    assert len(calls(tmp_path, "register")) == 1  # rotation changes no reference


def test_disable_deletes_every_key_disables_both_accounts_and_the_stored_keys(
    tmp_path: Path, shm: Path, store: Path
) -> None:
    assert create(tmp_path, shm, store).returncode == 0
    done = run(tmp_path, shm, store, "disable")
    assert done.returncode == 0, done.stderr
    accounts = state(tmp_path)["accounts"]
    assert isinstance(accounts, dict)
    for email in (SCAN_EMAIL, VERIFY_EMAIL):
        assert accounts[email] == {"keys": [], "disabled": True}
    assert list(store.iterdir()) == []


def test_a_failure_halfway_leaves_no_key_file_and_registers_nothing(
    tmp_path: Path, shm: Path, store: Path
) -> None:
    done = create_failing = run(
        tmp_path, shm, store, "create", "--connection", CONNECTION, FAKE_FAIL_KEY=VERIFY_EMAIL
    )
    assert create_failing.returncode != 0
    assert leftovers(shm) == [] and list(store.iterdir()) == []
    assert calls(tmp_path, "register") == []
    assert "PRIVATE KEY" not in done.stdout + done.stderr
    # Run again: the scan key the failed run created is deleted, only the stored one lives.
    assert create(tmp_path, shm, store).returncode == 0
    accounts = state(tmp_path)["accounts"]
    assert isinstance(accounts, dict)
    live = json.loads(stored(store, "google")["GOOGLEWORKSPACE_CREDENTIALS_CONTENT"])
    assert accounts[SCAN_EMAIL]["keys"] == [live["private_key_id"]]


def test_the_store_must_be_private_and_outside_any_repository(
    tmp_path: Path, shm: Path, store: Path
) -> None:
    store.chmod(0o755)
    refused = create(tmp_path, shm, store)
    assert refused.returncode != 0 and "store" in refused.stderr
    inside = tmp_path / "repo" / "secrets"
    inside.mkdir(parents=True, mode=0o700)
    (tmp_path / "repo" / ".git").mkdir()
    refused = run(tmp_path, shm, inside, "create", "--connection", CONNECTION)
    assert refused.returncode != 0 and "repository" in refused.stderr
    assert calls(tmp_path, "gcloud") == []


def test_a_key_folder_that_is_not_memory_is_refused(tmp_path: Path, store: Path) -> None:
    disk = tmp_path / "disk"
    disk.mkdir()
    refused = run(tmp_path, disk, store, "create", "--connection", CONNECTION)
    assert refused.returncode != 0 and "memory" in refused.stderr
    assert calls(tmp_path, "gcloud") == []


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["create", "--project", PROJECT, "--org", "not-a-uuid", "--store", "/x"], "org"),
        (["create", "--project", "Bad_Project", "--org", ORG, "--store", "/x"], "project"),
        (["create", "--project", PROJECT, "--org", ORG, "--store", "/x"], "connection"),
        (["destroy", "--project", PROJECT, "--org", ORG, "--store", "/x"], "usage"),
    ],
)
def test_arguments_are_checked_before_anything_runs(
    tmp_path: Path, args: list[str], message: str
) -> None:
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), **fakes(tmp_path)}
    done = subprocess.run(  # noqa: S603 - fixed argv: bash and the repository's script
        ["bash", str(SCRIPT), *args],  # noqa: S607 - bash from PATH, as the owner runs it
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0 and message in done.stderr
    assert calls(tmp_path, "gcloud") == []
