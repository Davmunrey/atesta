"""The PowerShell-backed check derivation, on a minimal synthetic Prowler tree."""

import importlib.util
from pathlib import Path
from types import ModuleType

TOOL = Path(__file__).resolve().parents[1] / "tools" / "powershell_checks.py"

SERVICE = """
class Exchange:
    def __init__(self, provider):
        if provider.graph:
            self.users = self._graph_users()
        self.transport_rules = []
        if self.powershell:
            if self.powershell.connect_exchange_online():
                self.transport_rules = self._get_transport_rules()
                self.mailboxes = self._get_mailboxes()
            self.powershell.close()
"""
CHECKS = {
    "exchange_rules_safe": "for rule in exchange_client.transport_rules: pass",
    "exchange_mailboxes_audited": "if exchange_client.users and exchange_client.mailboxes: pass",
    "exchange_users_named": "for user in exchange_client.users: pass",
    "exchange_other_client": "for rule in audit_client.transport_rules: pass",  # not the client
    "entra_users_named": "for user in entra_client.transport_rules: pass",  # other service
}


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("powershell_checks", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checks_reading_powershell_attributes_are_listed(tmp_path: Path) -> None:
    (tmp_path / "exchange").mkdir()
    (tmp_path / "exchange" / "exchange_service.py").write_text(SERVICE)
    for check, body in CHECKS.items():
        folder = tmp_path / check.split("_", 1)[0] / check
        folder.mkdir(parents=True)
        (folder / f"{check}.py").write_text(body)
    found = load().powershell_checks(tmp_path, sorted(CHECKS))
    assert found == ["exchange_mailboxes_audited", "exchange_rules_safe"]
