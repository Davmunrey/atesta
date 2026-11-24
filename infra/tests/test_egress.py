"""The scan egress allowlist (scanner-connectors spec, AWS runner; issue 454).

Static checks of infra/egress/envoy.yaml: each allowed host tunnels only to itself on 443, and
everything else is refused. CI also builds the image, runs `envoy --mode validate` and checks a
200 CONNECT for an allowed host and a 403 for any other (ci.yml, images job).
"""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG: dict[str, Any] = yaml.safe_load((ROOT / "infra/egress/envoy.yaml").read_text())
RESOURCES = CONFIG["static_resources"]
(LISTENER,) = RESOURCES["listeners"]
(CHAIN,) = LISTENER["filter_chains"]
(HCM,) = CHAIN["filters"]
MANAGER = HCM["typed_config"]
HOSTS_BY_VHOST = {
    v["name"]: v for v in MANAGER["route_config"]["virtual_hosts"] if v["name"] != "deny"
}
CLUSTERS = {c["name"]: c for c in RESOURCES["clusters"]}

# The spec's Runners table, Network row: M365 then Google Workspace.
ALLOWED = {
    "login.microsoftonline.com",
    "graph.microsoft.com",
    "management.azure.com",
    "oauth2.googleapis.com",
    "admin.googleapis.com",
    "cloudidentity.googleapis.com",
}
FORBIDDEN_DENY = {"status": 403}


def _cluster_address(name: str) -> tuple[str, int]:
    cluster = CLUSTERS[name]
    ((endpoint,),) = [e["lb_endpoints"] for e in cluster["load_assignment"]["endpoints"]]
    socket = endpoint["endpoint"]["address"]["socket_address"]
    return socket["address"], socket["port_value"]


def test_one_connect_listener_and_no_admin_interface() -> None:
    assert set(CONFIG) == {"static_resources"}  # no admin, no dynamic resources
    # The task's own interface; the proxy security group admits scan tasks only.
    assert LISTENER["address"]["socket_address"] == {"address": "0.0.0.0", "port_value": 3128}  # noqa: S104
    assert HCM["name"] == "envoy.filters.network.http_connection_manager"
    filters = [f["name"] for f in MANAGER["http_filters"]]
    assert filters == ["envoy.filters.http.router"]  # no dynamic forward proxy filter


def test_each_allowed_host_tunnels_only_to_itself_on_443() -> None:
    hosts = set()
    for name, vhost in HOSTS_BY_VHOST.items():
        (domain,) = vhost["domains"]
        host, port = domain.rsplit(":", 1)
        assert port == "443", name
        hosts.add(host)
        tunnel, refuse = vhost["routes"]
        assert tunnel["match"] == {"connect_matcher": {}}, name
        route = tunnel["route"]
        assert route["upgrade_configs"] == [{"upgrade_type": "CONNECT", "connect_config": {}}]
        assert _cluster_address(route["cluster"]) == (host, 443), name
        assert refuse == {"match": {"prefix": "/"}, "direct_response": FORBIDDEN_DENY}, name
    assert hosts == ALLOWED


def test_every_other_request_is_refused() -> None:
    (deny,) = [v for v in MANAGER["route_config"]["virtual_hosts"] if v["name"] == "deny"]
    assert deny["domains"] == ["*"]
    assert deny["routes"] == [
        {"match": {"connect_matcher": {}}, "direct_response": FORBIDDEN_DENY},
        {"match": {"prefix": "/"}, "direct_response": FORBIDDEN_DENY},
    ]


def test_clusters_are_fixed_names_never_chosen_by_the_client() -> None:
    assert len(CLUSTERS) == len(ALLOWED)
    for name, cluster in CLUSTERS.items():
        assert cluster["type"] == "LOGICAL_DNS", name  # not ORIGINAL_DST nor dynamic
        assert "cluster_type" not in cluster, name
        assert _cluster_address(name)[0] in ALLOWED, name


def test_the_access_log_records_the_authority_and_outcome_never_a_path() -> None:
    (log,) = MANAGER["access_log"]
    fields = log["typed_config"]["log_format"]["json_format"]
    assert fields["authority"] == "%REQ(:AUTHORITY)%"
    assert fields["code"] == "%RESPONSE_CODE%"
    assert not [v for v in fields.values() if "PATH" in str(v) or "BODY" in str(v)]


def test_the_spec_lists_every_allowed_host() -> None:
    spec = (ROOT / "docs/specs/scanner-connectors.md").read_text()
    (network,) = [line for line in spec.splitlines() if line.startswith("| Network |")]
    for host in ALLOWED:
        assert host in network, host


def test_the_image_pins_envoy_by_digest_and_runs_unprivileged() -> None:
    dockerfile = (ROOT / "infra/egress/Dockerfile").read_text().splitlines()
    (base,) = [line for line in dockerfile if line.startswith("FROM ")]
    assert base.startswith("FROM envoyproxy/envoy:distroless-v")
    assert "@sha256:" in base and len(base.rsplit("@sha256:", 1)[1]) == 64
    assert "USER 10001" in dockerfile
