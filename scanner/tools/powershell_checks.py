"""List the M365 checks that read PowerShell data, from a Prowler source tree.

Usage: python -I scanner/tools/powershell_checks.py <site-packages>/prowler/providers/m365/services
       <scanner/expected/<version>/m365.json>  > m365-powershell.json

A service fills some attributes only inside `if self.powershell:` in its constructor; a check is
PowerShell-backed when it reads any of them through `<service>_client`. Static analysis of the
pinned source, so the image build can re-run it and compare (scanner-connectors spec, D1).
"""

import ast
import json
import sys
from pathlib import Path


def powershell_attributes(service_file: Path) -> set[str]:
    attributes: set[str] = set()
    for node in ast.walk(ast.parse(service_file.read_text())):
        if isinstance(node, ast.If) and ast.unparse(node.test) == "self.powershell":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assign):
                    attributes.update(
                        t.attr
                        for t in inner.targets
                        if isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "self"
                    )
    return attributes


def client_reads(check_file: Path, service: str) -> set[str]:
    return {
        node.attr
        for node in ast.walk(ast.parse(check_file.read_text()))
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == f"{service}_client"
    }


def powershell_checks(services: Path, listed: list[str]) -> list[str]:
    cache: dict[str, set[str]] = {}
    found = []
    for check in listed:
        service = check.split("_", 1)[0]
        if service not in cache:
            service_file = services / service / f"{service}_service.py"
            cache[service] = powershell_attributes(service_file) if service_file.exists() else set()
        if client_reads(services / service / check / f"{check}.py", service) & cache[service]:
            found.append(check)
    return sorted(found)


def main() -> None:
    services, listed_file = Path(sys.argv[1]), Path(sys.argv[2])
    listed = json.loads(listed_file.read_text())["m365"]
    print(json.dumps({"m365": powershell_checks(services, listed)}, indent=2))


if __name__ == "__main__":
    main()
