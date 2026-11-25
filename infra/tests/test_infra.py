"""Static checks of the OpenTofu code (infra-dev spec): no AWS credentials needed.

Each assertion pins a setting the identity spec requires; several cannot change after the pool
exists (username attributes, case sensitivity), so a drift must fail before any apply.
"""

import json
from pathlib import Path
from typing import Any

import hcl2
import yaml

INFRA = Path(__file__).resolve().parents[1]


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            _clean(k): _clean(v)
            for k, v in value.items()
            if k not in ("__is_block__", "__comments__")
        }
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, str) and len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def load(path: str) -> dict[str, Any]:
    with (INFRA / path).open() as handle:
        parsed: dict[str, Any] = _clean(hcl2.load(handle))
    return parsed


def resources(path: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for block in load(path).get("resource", []):
        for kind, named in block.items():
            for name, body in named.items():
                out[f"{kind}.{name}"] = body
    return out


COGNITO = resources("modules/cognito/main.tf")
POOL = COGNITO["aws_cognito_user_pool.this"]
CLIENT = COGNITO["aws_cognito_user_pool_client.web"]


def test_pool_enforces_mfa_and_immutable_username_settings() -> None:
    assert (POOL["user_pool_tier"], POOL["deletion_protection"], POOL["mfa_configuration"]) == (
        "ESSENTIALS",
        "ACTIVE",
        "ON",
    )
    assert POOL["software_token_mfa_configuration"] == [{"enabled": True}]
    assert "sms_configuration" not in POOL and "sms_authentication_message" not in POOL
    assert POOL["username_attributes"] == ["email"]
    assert POOL["username_configuration"] == [{"case_sensitive": False}]
    assert POOL["auto_verified_attributes"] == ["email"]
    assert POOL["user_attribute_update_settings"] == [
        {"attributes_require_verification_before_update": ["email"]}
    ]


def test_pool_recovery_password_and_email_schema() -> None:
    mechanisms = POOL["account_recovery_setting"][0]["recovery_mechanism"]
    assert [m["name"] for m in mechanisms] == ["verified_email"]
    assert POOL["password_policy"][0]["minimum_length"] == 12
    assert POOL["admin_create_user_config"] == [{"allow_admin_create_user_only": False}]
    email = next(s for s in POOL["schema"] if s["name"] == "email")
    assert email["required"] is True  # every client may write a required attribute at sign-up


def test_managed_login_v2_with_branding() -> None:
    assert COGNITO["aws_cognito_user_pool_domain.this"]["managed_login_version"] == 2
    branding = COGNITO["aws_cognito_managed_login_branding.web"]
    assert branding["use_cognito_provided_values"] is True


def test_app_client_is_public_pkce_without_admin_scope() -> None:
    assert CLIENT["generate_secret"] is False
    assert CLIENT["allowed_oauth_flows"] == ["code"]
    assert CLIENT["allowed_oauth_scopes"] == ["openid", "email"]
    assert CLIENT["explicit_auth_flows"] == ["ALLOW_REFRESH_TOKEN_AUTH"]
    assert CLIENT["write_attributes"] and "email" not in CLIENT["write_attributes"]
    assert (CLIENT["access_token_validity"], CLIENT["id_token_validity"]) == (30, 30)
    assert CLIENT["refresh_token_validity"] == 12
    assert CLIENT["token_validity_units"] == [
        {"access_token": "minutes", "id_token": "minutes", "refresh_token": "hours"}
    ]


def test_email_template_is_spanish_first_with_one_code_placeholder() -> None:
    es = json.loads((INFRA / "i18n/cognito.es.json").read_text())
    en = json.loads((INFRA / "i18n/cognito.en.json").read_text())
    assert es["verification_message"].count("{####}") == 1
    assert "{####}" not in en["verification_message"]
    template = POOL["verification_message_template"][0]
    assert template["email_message"].startswith("${local.es.")


def test_dev_state_and_versions_are_pinned() -> None:
    dev = load("envs/dev/main.tf")["terraform"][0]
    backend = dev["backend"][0]["s3"]
    assert (backend["use_lockfile"], backend["encrypt"], backend["region"]) == (
        True,
        True,
        "eu-south-2",
    )
    assert dev["required_version"] == f"= {(INFRA / '.opentofu-version').read_text().strip()}"
    assert dev["required_providers"][0]["aws"]["version"] == "= 6.73.0"


def test_github_roles_are_scoped_to_pull_requests_and_the_protected_environment() -> None:
    oidc = load("modules/github-oidc/main.tf")
    trust = next(
        d
        for d in oidc["data"]
        if "aws_iam_policy_document" in d and "trust" in d["aws_iam_policy_document"]
    )
    subjects = trust["aws_iam_policy_document"]["trust"]["for_each"]
    assert subjects == {
        "plan": "repo:${var.repository}:pull_request",
        "apply": "repo:${var.repository}:environment:${var.apply_environment}",
    }
    condition = trust["aws_iam_policy_document"]["trust"]["statement"][0]["condition"]
    assert {c["test"] for c in condition} == {"StringEquals"}  # no wildcard subjects


# Hosted environment (hosted-environment spec): security settings of the base modules.

KMS = resources("modules/kms/main.tf")
EVIDENCE = resources("modules/s3-evidence/main.tf")
NETWORK = resources("modules/network/main.tf")


def test_every_key_rotates_and_waits_before_deletion() -> None:
    keys = {name: body for name, body in KMS.items() if name.startswith("aws_kms_key.")}
    assert set(keys) == {
        "aws_kms_key.database",
        "aws_kms_key.evidence",
        "aws_kms_key.secrets",
        "aws_kms_key.logs",
        "aws_kms_key.queues",
    }
    for name, key in keys.items():
        assert key["enable_key_rotation"] is True, name
        assert key["deletion_window_in_days"] == 30, name


def test_the_evidence_bucket_is_private_encrypted_versioned_and_tls_only() -> None:
    block = EVIDENCE["aws_s3_bucket_public_access_block.this"]
    assert all(
        block[k] is True
        for k in (
            "block_public_acls",
            "block_public_policy",
            "ignore_public_acls",
            "restrict_public_buckets",
        )
    )
    assert (
        EVIDENCE["aws_s3_bucket_versioning.this"]["versioning_configuration"][0]["status"]
        == "Enabled"
    )
    sse = EVIDENCE["aws_s3_bucket_server_side_encryption_configuration.this"]["rule"][0]
    assert sse["apply_server_side_encryption_by_default"][0]["sse_algorithm"] == "aws:kms"
    assert (
        EVIDENCE["aws_s3_bucket_ownership_controls.this"]["rule"][0]["object_ownership"]
        == "BucketOwnerEnforced"
    )
    policy = load("modules/s3-evidence/main.tf")["data"]
    document = next(
        b["aws_iam_policy_document"]["bucket"] for b in policy if "aws_iam_policy_document" in b
    )
    statement = next(s for s in document["statement"] if s.get("sid") == "DenyInsecureTransport")
    assert (
        statement["effect"] == "Deny"
        and statement["condition"][0]["variable"] == "aws:SecureTransport"
    )


def test_the_evidence_bucket_locks_every_version_for_a_year_in_governance_mode() -> None:
    """#263, owner 2026-11-23: Object Lock in governance mode, 365 days by default."""
    assert EVIDENCE["aws_s3_bucket.this"]["object_lock_enabled"] is True
    lock = EVIDENCE["aws_s3_bucket_object_lock_configuration.this"]
    retention = lock["rule"][0]["default_retention"][0]
    assert (retention["mode"], retention["days"]) == ("GOVERNANCE", 365)
    assert "${aws_s3_bucket_versioning.this}" in lock.get("depends_on", [])


def test_no_principal_may_bypass_the_evidence_lock() -> None:
    """An explicit deny in the bucket policy beats any allow, the deploy role's s3:* included.

    Erasing locked evidence (a GDPR request) means changing this policy first, which CloudTrail
    records (hosted-environment spec, Evidence bucket).
    """
    data = load("modules/s3-evidence/main.tf")["data"]
    document = next(
        b["aws_iam_policy_document"]["bucket"] for b in data if "aws_iam_policy_document" in b
    )
    deny = next(s for s in document["statement"] if s.get("sid") == "DenyGovernanceBypass")
    assert deny["effect"] == "Deny"
    assert deny["actions"] == ["s3:BypassGovernanceRetention"]
    assert deny["principals"][0] == {"type": "*", "identifiers": ["*"]}
    assert "condition" not in deny
    policy = EVIDENCE["aws_s3_bucket_policy.this"]
    assert policy["policy"] == "${data.aws_iam_policy_document.bucket.json}"


def test_private_subnets_take_no_public_addresses_and_flow_logs_are_on() -> None:
    for kind in ("public", "private"):
        assert NETWORK[f"aws_subnet.{kind}"]["map_public_ip_on_launch"] is False
    private_routes = NETWORK["aws_route_table.private"]["route"][0]
    assert "nat_gateway_id" in private_routes and "gateway_id" not in private_routes
    assert NETWORK["aws_flow_log.this"]["traffic_type"] == "ALL"
    assert "kms_key_id" in NETWORK["aws_cloudwatch_log_group.flow"]


RDS = resources("modules/rds/main.tf")
RDS_VARS = {k: v for b in load("modules/rds/main.tf")["variable"] for k, v in b.items()}


def test_the_database_is_postgres_18_encrypted_private_and_protected() -> None:
    db = RDS["aws_db_instance.this"]
    assert (db["engine"], db["engine_version"]) == ("postgres", "18")
    assert db["storage_encrypted"] is True and db["kms_key_id"] == "${var.kms_key_arn}"
    assert db["publicly_accessible"] is False
    assert db["deletion_protection"] is True and db["skip_final_snapshot"] is False
    assert db["manage_master_user_password"] is True  # master secret lives in Secrets Manager
    assert db["master_user_secret_kms_key_id"] == "${var.kms_key_arn}"
    assert "password" not in db
    assert db["iam_database_authentication_enabled"] is False
    assert db["multi_az"] == "${var.multi_az}"
    assert db["backup_retention_period"] == "${var.backup_retention_days}"
    assert db["copy_tags_to_snapshot"] is True and db["auto_minor_version_upgrade"] is True


def test_backups_are_14_days_in_dev_and_at_most_35() -> None:
    retention = RDS_VARS["backup_retention_days"]
    assert retention["default"] == 14
    rule = retention["validation"][0]["condition"]
    assert "var.backup_retention_days >= 14" in rule and "var.backup_retention_days <= 35" in rule


def test_the_database_requires_tls_and_logs_without_statements() -> None:
    params = {p["name"]: p["value"] for p in RDS["aws_db_parameter_group.this"]["parameter"]}
    assert params["rds.force_ssl"] == "1"
    assert params["log_statement"] == "none"  # statements may carry customer data (rule 2)
    assert params["log_min_duration_statement"] == "-1"
    # PostgreSQL 18 made log_connections a list; RDS documents this list as the old "1" (#299).
    assert params["log_connections"] == "receipt,authentication,authorization"
    assert RDS["aws_cloudwatch_log_group.postgres"]["kms_key_id"] == "${var.logs_key_arn}"
    assert "retention_in_days" in RDS["aws_cloudwatch_log_group.postgres"]


def test_rds_ci_and_compose_run_the_same_postgres_major() -> None:
    """Engine major, parameter group family and the CI/compose image move together (#299)."""
    db = RDS["aws_db_instance.this"]
    group = RDS["aws_db_parameter_group.this"]
    compose = yaml.safe_load((INFRA.parent / "compose.yaml").read_text())
    image = compose["services"]["postgres"]["image"]
    tag = image.split("@", 1)[0].split(":", 1)[1]
    assert image.startswith("postgres:") and "@sha256:" in image
    assert db["engine_version"] == tag.split(".")[0] == "18"
    assert group["family"] == f"postgres{db['engine_version']}"
    assert group["name"] == f"${{var.name}}-pg{db['engine_version']}"


def test_only_the_application_security_group_reaches_the_database() -> None:
    rule = RDS["aws_vpc_security_group_ingress_rule.from_app"]
    assert (rule["from_port"], rule["to_port"], rule["ip_protocol"]) == (5432, 5432, "tcp")
    assert "cidr_ipv4" not in rule and "referenced_security_group_id" in rule
    ingress = [k for k in RDS if k.startswith("aws_vpc_security_group_ingress_rule.")]
    assert ingress == ["aws_vpc_security_group_ingress_rule.from_app"]
    assert RDS["aws_db_subnet_group.this"]["subnet_ids"] == "${var.private_subnet_ids}"


def test_role_connection_secrets_are_encrypted_and_hold_no_value_in_code() -> None:
    secrets = {k: v for k, v in RDS.items() if k.startswith("aws_secretsmanager_secret.")}
    assert set(secrets) == {
        "aws_secretsmanager_secret.app_url",
        "aws_secretsmanager_secret.migration_url",
        "aws_secretsmanager_secret.operator_url",  # ADR-017: the operator service's own login
    }
    for name, secret in secrets.items():
        assert secret["kms_key_id"] == "${var.secrets_key_arn}", name
    assert not [k for k in RDS if k.startswith("aws_secretsmanager_secret_version.")]


SES = resources("modules/ses/main.tf")


def test_ses_identity_signs_with_dkim_and_uses_its_own_mail_from() -> None:
    identity = SES["aws_sesv2_email_identity.this"]
    assert identity["dkim_signing_attributes"] == [{"next_signing_key_length": "RSA_2048_BIT"}]
    assert (
        identity["configuration_set_name"]
        == "${aws_sesv2_configuration_set.this.configuration_set_name}"
    )
    mail_from = SES["aws_sesv2_email_identity_mail_from_attributes.this"]
    assert mail_from["behavior_on_mx_failure"] == "REJECT_MESSAGE"


def test_ses_requires_tls_and_suppresses_bounces_and_complaints() -> None:
    config = SES["aws_sesv2_configuration_set.this"]
    assert config["delivery_options"] == [{"tls_policy": "REQUIRE"}]
    assert sorted(config["suppression_options"][0]["suppressed_reasons"]) == [
        "BOUNCE",
        "COMPLAINT",
    ]
    assert config["reputation_options"] == [{"reputation_metrics_enabled": True}]


ECS_FILE = load("modules/ecs/main.tf")
ECS = resources("modules/ecs/main.tf")
CONTAINERS = ECS_FILE["locals"][0]["containers"]
ECS_VARS = {k: v for b in ECS_FILE["variable"] for k, v in b.items()}
ECS_POLICIES = {
    name: body
    for block in ECS_FILE["data"]
    for kind, named in block.items()
    if kind == "aws_iam_policy_document"
    for name, body in named.items()
}


def test_every_container_is_locked_down_and_logs_to_its_own_group() -> None:
    locked = ECS_FILE["locals"][0]["locked"]
    assert locked["readonlyRootFilesystem"] is True and locked["privileged"] is False
    assert locked["user"] == "10001"
    assert locked["linuxParameters"]["capabilities"]["drop"] == ["ALL"]
    assert set(CONTAINERS) == {
        "api",
        "worker",
        "migrate",
        "bootstrap",
        "scan",
        "egress",
        "operator",
    }
    for name, container in CONTAINERS.items():
        assert container.startswith("${merge(local.locked, {"), name
        assert 'logDriver = "awslogs"' in container, name
        group = "migrate" if name == "bootstrap" else name  # one-off tasks share a group
        assert f'aws_cloudwatch_log_group.this["{group}"].name' in container, name


def test_secrets_come_only_from_secrets_manager_never_from_plain_environment() -> None:
    for name in ("api", "worker", "migrate", "bootstrap"):
        assert f"secrets = [for k, arn in var.secrets.{name} :" in CONTAINERS[name], name
    assert (
        "secrets" not in CONTAINERS["scan"]
    )  # the wrapper reads its credential with the task role
    rule = ECS_VARS["environment"]["validation"][0]["condition"]
    assert "DATABASE_URL|_KEY|SECRET|PASSWORD|TOKEN" in rule
    exec_policy = ECS_POLICIES["execution"]["statement"]
    read = next(s for s in exec_policy if "secretsmanager:GetSecretValue" in s["actions"])
    assert read["resources"] == "${local.secret_arns}"  # listed ARNs only, JSON-key suffix removed


def test_images_are_pinned_by_digest_and_registries_are_immutable() -> None:
    rule = ECS_VARS["images"]["validation"][0]["condition"]
    assert "@sha256:[0-9a-f]{64}$" in rule
    repos = resources("modules/ecr/main.tf")["aws_ecr_repository.this"]
    assert repos["for_each"] == '${toset(["api", "worker", "scan", "egress", "operator"])}'
    assert repos["image_tag_mutability"] == "IMMUTABLE"
    assert repos["image_scanning_configuration"] == [{"scan_on_push": True}]
    assert repos["encryption_configuration"][0]["encryption_type"] == "KMS"


def test_services_run_on_fargate_in_private_subnets_and_roll_back() -> None:
    for name in ("worker",):
        service = ECS[f"aws_ecs_service.{name}"]
        assert service["launch_type"] == "FARGATE", name
        network = service["network_configuration"][0]
        assert network["assign_public_ip"] is False, name
        assert network["subnets"] == "${var.private_subnet_ids}", name
        breaker = service["deployment_circuit_breaker"][0]
        assert breaker == {"enable": True, "rollback": True}, name
    task = ECS["aws_ecs_task_definition.this"]
    assert task["network_mode"] == "awsvpc" and task["requires_compatibilities"] == ["FARGATE"]


def test_one_scan_task_definition_with_no_baked_role_and_no_way_out_but_the_proxy() -> None:
    """Issue 454: the proxy, the VPC endpoints and S3's gateway; never 0.0.0.0/0."""
    scan = ECS["aws_ecs_task_definition.scan"]
    assert "task_role_arn" not in scan  # ADR-004: the worker passes the per-org role per run
    assert (scan["cpu"], scan["memory"]) == ("2048", "4096")  # scanner-connectors D13
    rules = {
        k.removeprefix("aws_vpc_security_group_egress_rule."): v
        for k, v in ECS.items()
        if k.startswith("aws_vpc_security_group_egress_rule.scan")
    }
    assert set(rules) == {"scan_proxy", "scan_endpoints", "scan_s3"}
    assert all(r["security_group_id"] == "${aws_security_group.scan.id}" for r in rules.values())
    assert not [r for r in rules.values() if "cidr_ipv4" in r or "cidr_ipv6" in r]
    proxy, endpoints, s3 = rules["scan_proxy"], rules["scan_endpoints"], rules["scan_s3"]
    assert proxy["referenced_security_group_id"] == "${aws_security_group.egress.id}"
    assert (proxy["from_port"], proxy["to_port"]) == (3128, 3128)
    assert endpoints["referenced_security_group_id"] == "${var.endpoints_security_group_id}"
    assert s3["prefix_list_id"] == "${var.s3_prefix_list_id}"
    for rule in (endpoints, s3):
        assert (rule["from_port"], rule["to_port"]) == (443, 443)
    assert not [k for k in ECS if k.startswith("aws_vpc_security_group_ingress_rule.scan")]


def test_the_worker_may_only_start_scans_with_bounded_roles() -> None:
    statements = {s["sid"]: s for s in ECS_POLICIES["worker"]["statement"]}
    assert statements["RunScans"]["actions"] == ["ecs:RunTask"]
    assert statements["RunScans"]["resources"] == ["${local.scan_family_arn}:*"]
    passable = statements["PassScanRoles"]["resources"]
    assert "${aws_iam_role.scan_execution.arn}" in passable
    assert "arn:aws:iam::${local.account}:role/atesta-scan/${var.name}/*" in passable
    boundary = ECS_POLICIES["scan_boundary"]["statement"]
    assert all("*" not in s["actions"] for s in boundary)
    assert all(s["resources"] != ["*"] for s in boundary)


def test_every_log_group_is_encrypted_and_expires() -> None:
    group = ECS["aws_cloudwatch_log_group.this"]
    assert group["kms_key_id"] == "${var.logs_key_arn}"
    assert group["retention_in_days"] == "${var.log_retention_days}"


EDGE = resources("modules/ecs/api.tf")
WEB_FILE = load("modules/web/main.tf")
WEB = resources("modules/web/main.tf")
WEB_VARS = {k: v for b in WEB_FILE["variable"] for k, v in b.items()}


def test_the_api_service_runs_privately_behind_its_load_balancer() -> None:
    service = EDGE["aws_ecs_service.api"]
    assert service["launch_type"] == "FARGATE"
    network = service["network_configuration"][0]
    assert network["assign_public_ip"] is False
    assert network["subnets"] == "${var.private_subnet_ids}"
    assert service["deployment_circuit_breaker"][0] == {"enable": True, "rollback": True}
    assert service["load_balancer"][0]["container_port"] == 8000
    assert EDGE["aws_lb_target_group.api"]["health_check"][0]["path"] == "/health"


def test_the_load_balancer_takes_only_cloudfront_over_tls_1_3() -> None:
    alb = EDGE["aws_lb.api"]
    assert alb["drop_invalid_header_fields"] is True
    assert alb["access_logs"] == [{"bucket": "${aws_s3_bucket.alb_logs.id}", "enabled": True}]
    sse = EDGE["aws_s3_bucket_server_side_encryption_configuration.alb_logs"]["rule"][0]
    assert sse["apply_server_side_encryption_by_default"][0]["sse_algorithm"] == "AES256"
    listeners = [k for k in EDGE if k.startswith("aws_lb_listener.")]
    assert listeners == ["aws_lb_listener.https"]
    assert (
        EDGE["aws_lb_listener.https"]["ssl_policy"] == "ELBSecurityPolicy-TLS13-1-2-Res-PQ-2025-09"
    )
    ingress = {
        k: v for k, v in EDGE.items() if k.startswith("aws_vpc_security_group_ingress_rule.")
    }
    alb_in = ingress["aws_vpc_security_group_ingress_rule.alb_from_cloudfront"]
    assert alb_in["prefix_list_id"] == "${data.aws_ec2_managed_prefix_list.cloudfront.id}"
    assert all("cidr_ipv4" not in rule for rule in ingress.values())


def test_the_site_bucket_is_private_and_read_only_through_this_distribution() -> None:
    block = WEB["aws_s3_bucket_public_access_block.site"]
    assert all(block[k] is True for k in ("block_public_acls", "block_public_policy"))
    assert all(block[k] is True for k in ("ignore_public_acls", "restrict_public_buckets"))
    oac = WEB["aws_cloudfront_origin_access_control.site"]
    assert (oac["signing_behavior"], oac["signing_protocol"]) == ("always", "sigv4")
    policy = next(
        b["aws_iam_policy_document"]["site"]
        for b in WEB_FILE["data"]
        if "aws_iam_policy_document" in b
    )
    read = next(s for s in policy["statement"] if s["sid"] == "CloudFrontReads")
    assert read["actions"] == ["s3:GetObject"]
    assert read["condition"][0]["values"] == ["${aws_cloudfront_distribution.this.arn}"]


def test_security_headers_follow_the_web_shell_spec() -> None:
    for name, referrer in (("default", "same-origin"), ("no_referrer", "no-referrer")):
        headers = WEB[f"aws_cloudfront_response_headers_policy.{name}"]["security_headers_config"][
            0
        ]
        csp = headers["content_security_policy"][0]
        assert csp["content_security_policy"] == "${var.content_security_policy}", name
        hsts = headers["strict_transport_security"][0]
        assert hsts["access_control_max_age_sec"] >= 31536000 and hsts["include_subdomains"] is True
        assert headers["content_type_options"][0]["override"] is True, name
        assert headers["frame_options"][0]["frame_option"] == "DENY", name
        assert headers["referrer_policy"][0]["referrer_policy"] == referrer, name
    limit = WEB_VARS["content_security_policy"]["validation"][0]["condition"]
    assert "length(var.content_security_policy) <= 1783" in limit  # scripts/csp.ts limit


def test_the_distribution_routes_api_and_private_pages_and_forces_https() -> None:
    dist = WEB["aws_cloudfront_distribution.this"]
    default = dist["default_cache_behavior"][0]
    assert default["viewer_protocol_policy"] == "redirect-to-https"
    behaviors = {b["path_pattern"]: b for b in dist["ordered_cache_behavior"]}
    assert set(behaviors) == {"/api/*", "/auth/*", "/invite*", "/training*", "/unsubscribe*"}
    assert "custom_error_response" not in dist  # would rewrite the API's own error responses
    for path in ("/api/*", "/auth/*"):
        assert behaviors[path]["target_origin_id"] == "api", path
        assert behaviors[path]["viewer_protocol_policy"] == "https-only", path
    for path in ("/invite*", "/training*", "/unsubscribe*"):  # tokens in the URL
        policy = behaviors[path]["response_headers_policy_id"]
        assert policy == "${aws_cloudfront_response_headers_policy.no_referrer.id}", path
    assert dist["viewer_certificate"][0]["minimum_protocol_version"] == "TLSv1.2_2021"
    assert dist["viewer_certificate"][0]["ssl_support_method"] == "sni-only"
    api = next(o for o in dist["origin"] if o["origin_id"] == "api")
    origin = api["custom_origin_config"][0]
    assert origin["origin_protocol_policy"] == "https-only"
    assert origin["origin_ssl_protocols"] == ["TLSv1.2"]


def _modules(env: str) -> dict[str, Any]:
    return {k: v for m in load(f"envs/{env}/main.tf")["module"] for k, v in m.items()}


def test_prod_uses_the_same_platform_as_dev_with_prod_sizes() -> None:
    dev, prod = _modules("dev")["platform"], _modules("prod")["platform"]
    assert dev["source"] == prod["source"] == "../../modules/platform"
    assert (dev["multi_az"], dev["backup_retention_days"], dev["nat_per_az"]) == (False, 14, False)
    assert (prod["multi_az"], prod["backup_retention_days"], prod["nat_per_az"]) == (True, 35, True)
    assert prod["api_count"] >= 2
    platform = {k: v for m in load("modules/platform/main.tf")["module"] for k, v in m.items()}
    assert platform["database"]["kms_key_arn"] == "${module.kms.database_key_arn}"
    assert platform["ses_notifications"]["count"] == "${var.mail_domain == null ? 0 : 1}"
    assert "providers" not in platform["ses_notifications"]  # eu-south-2


def test_prod_has_its_own_state_and_apply_environment() -> None:
    prod = load("envs/prod/main.tf")
    assert prod["terraform"][0]["backend"][0]["s3"]["key"] == "prod/terraform.tfstate"
    assert _modules("prod")["github_oidc"]["apply_environment"] == "prod"


def test_cognito_email_in_prod_uses_ses_in_paris_and_nothing_else_leaves_spain() -> None:
    prod = load("envs/prod/main.tf")
    aliases = {
        p["aws"]["alias"]: p["aws"]["region"] for p in prod["provider"] if "alias" in p["aws"]
    }
    assert aliases == {"paris": "eu-west-3"}  # ADR-007 amendment 1, the only EU exception
    modules = _modules("prod")
    assert modules["ses_cognito"]["providers"] == {"aws": "${aws.paris}"}
    assert [k for k, v in modules.items() if "providers" in v] == ["ses_cognito"]
    assert modules["cognito"]["email_sending_account"] == "DEVELOPER"
    assert modules["cognito"]["ses_source_arn"] == "${module.ses_cognito.identity_arn}"


def test_the_apply_role_manages_only_what_the_platform_uses() -> None:
    oidc = load("modules/github-oidc/main.tf")
    apply = next(
        d["aws_iam_policy_document"]["apply"]
        for d in oidc["data"]
        if "apply" in d.get("aws_iam_policy_document", {})
    )
    actions = [a for s in apply["statement"] for a in s["actions"]]
    assert "*" not in actions and "*:*" not in actions
    iam = next(s for s in apply["statement"] if s.get("sid") == "OwnIam")
    assert all(
        ":role/${var.name}-" in r
        or "atesta-scan" in r
        or "policy/${var.name}-" in r
        or "oidc-provider" in r
        for r in iam["resources"]
    )
    roles = resources("modules/github-oidc/main.tf")["aws_iam_role.github"]
    assert roles["name"] == "${var.name}-${each.key}"
    assert _modules("prod")["github_oidc"]["name"] == "atesta-prod"


def test_the_bootstrap_task_gets_the_master_password_only_as_a_secret() -> None:
    platform = {k: v for m in load("modules/platform/main.tf")["module"] for k, v in m.items()}
    bootstrap = platform["ecs"]["secrets"]["bootstrap"]
    assert bootstrap["ATESTA_MASTER_PASSWORD"] == "${module.database.master_secret_arn}:password::"
    assert platform["ecs"]["decrypt_key_arns"] == ["${module.kms.database_key_arn}"]
    assert "db_bootstrap" in CONTAINERS["bootstrap"]


def _alerts(env: str) -> tuple[str, list[str]]:
    budget = resources(f"envs/{env}/budgets.tf")["aws_budgets_budget.monthly"]
    thresholds = budget["dynamic"][0]["notification"]["for_each"]
    return budget["limit_amount"], thresholds


def test_budget_alerts_are_150_250_400_in_dev_and_250_350_450_in_prod() -> None:
    assert _alerts("dev") == ("400", '${toset(["150", "250", "400"])}')
    assert _alerts("prod") == ("450", '${toset(["250", "350", "450"])}')


# --- evidence file uploads (evidence-file-uploads spec, #222) -------------------------------


def test_the_api_may_only_put_uploaded_evidence_and_read_it_once_scanned_clean() -> None:
    """evidence-malware-scanning spec: the read is bound to GuardDuty's tag on that version."""
    statements = {s["sid"]: s for s in ECS_POLICIES["api"]["statement"]}
    assert set(statements) == {"EvidenceUploads", "EvidenceReadsWhenClean", "EvidenceKey"}
    uploads, reads = statements["EvidenceUploads"], statements["EvidenceReadsWhenClean"]
    assert uploads["actions"] == ["s3:PutObject"]  # no delete, no list, no tagging
    assert reads["actions"] == ["s3:GetObject", "s3:GetObjectVersion"]
    for statement in (uploads, reads):  # not scan outputs
        assert statement["resources"] == ["${var.evidence_bucket_arn}/*/evidence/*"]
    assert "condition" not in uploads
    assert reads["condition"] == [
        {
            "test": "StringEquals",
            "variable": "s3:ExistingObjectTag/GuardDutyMalwareScanStatus",
            "values": ["NO_THREATS_FOUND"],
        }
    ]
    key = statements["EvidenceKey"]
    assert key["actions"] == ["kms:Decrypt", "kms:GenerateDataKey"]
    assert key["resources"] == ["${var.evidence_key_arn}"]
    attached = ECS["aws_iam_role_policy.api"]
    assert attached["role"] == "${aws_iam_role.api.id}"
    assert attached["policy"] == "${data.aws_iam_policy_document.api.json}"


def test_the_platform_points_the_services_at_the_evidence_bucket() -> None:
    platform = {k: v for m in load("modules/platform/main.tf")["module"] for k, v in m.items()}
    ecs = platform["ecs"]
    assert ecs["evidence_key_arn"] == "${module.kms.evidence_key_arn}"
    assert ecs["environment"] == "${local.app_environment}"
    (environment,) = [
        block["app_environment"]
        for block in load("modules/platform/main.tf")["locals"]
        if "app_environment" in block
    ]
    assert 'ATESTA_EVIDENCE_STORE = "s3"' in environment
    assert "ATESTA_EVIDENCE_BUCKET = module.evidence.bucket_name" in environment
    assert "AWS_DEFAULT_REGION" in environment  # boto3 takes its region from this variable
    # Later arguments win in merge(): a hand-set value cannot point the API at another bucket.
    assert environment.startswith("${merge(var.app_environment, {")


# --- malware scanning (evidence-malware-scanning spec, #430) ---------------------------------

EVIDENCE_FILE = load("modules/s3-evidence/main.tf")
EVIDENCE_DOCS = {
    name: body
    for block in EVIDENCE_FILE["data"]
    for kind, named in block.items()
    if kind == "aws_iam_policy_document"
    for name, body in named.items()
}
PLATFORM_FILE = load("modules/platform/main.tf")
PLATFORM = resources("modules/platform/main.tf")
PLATFORM_DOCS = {
    name: body
    for block in PLATFORM_FILE.get("data", [])
    for kind, named in block.items()
    if kind == "aws_iam_policy_document"
    for name, body in named.items()
}


def test_guardduty_scans_the_whole_evidence_bucket_and_tags_each_result() -> None:
    """Prefixes are literal (at most 5) and keys start with the organization id (spec D2)."""
    plan = EVIDENCE["aws_guardduty_malware_protection_plan.evidence"]
    assert plan["role"] == "${aws_iam_role.malware_scan.arn}"
    bucket = plan["protected_resource"][0]["s3_bucket"][0]
    assert bucket == {"bucket_name": "${aws_s3_bucket.this.id}"}
    assert plan["actions"][0]["tagging"][0]["status"] == "ENABLED"
    assert "${aws_iam_role_policy.malware_scan}" in plan["depends_on"]


def test_the_scan_role_follows_the_aws_template_for_this_bucket_only() -> None:
    trust = EVIDENCE_DOCS["malware_scan_trust"]["statement"][0]
    assert trust["actions"] == ["sts:AssumeRole"]
    assert trust["principals"][0]["identifiers"] == [
        "malware-protection-plan.guardduty.amazonaws.com"
    ]
    statements = {s["sid"]: s for s in EVIDENCE_DOCS["malware_scan"]["statement"]}
    assert set(statements) == {
        "AllowManagedRuleToSendS3EventsToGuardDuty",
        "AllowGuardDutyToMonitorEventBridgeManagedRule",
        "AllowPostScanTag",
        "AllowEnableS3EventBridgeEvents",
        "AllowPutValidationObject",
        "AllowCheckBucketOwnership",
        "AllowMalwareScan",
        "AllowDecryptForMalwareScan",
    }
    for statement in statements.values():
        assert "*" not in statement["resources"] and "*" not in statement["actions"]
    objects = "${aws_s3_bucket.this.arn}/*"
    assert statements["AllowMalwareScan"]["resources"] == [objects]
    assert statements["AllowPostScanTag"]["resources"] == [objects]
    assert statements["AllowPutValidationObject"]["resources"] == [
        "${aws_s3_bucket.this.arn}/malware-protection-resource-validation-object"
    ]
    kms = statements["AllowDecryptForMalwareScan"]
    assert kms["resources"] == ["${var.kms_key_arn}"]
    assert kms["condition"][0]["variable"] == "kms:ViaService"
    rule = statements["AllowManagedRuleToSendS3EventsToGuardDuty"]
    assert rule["condition"][0]["values"] == ["malware-protection-plan.guardduty.amazonaws.com"]


def test_only_the_scan_role_may_write_the_scan_tag() -> None:
    bucket = {s["sid"]: s for s in EVIDENCE_DOCS["bucket"]["statement"]}
    deny = bucket["DenyScanTagWritesButGuardDuty"]
    assert deny["effect"] == "Deny"
    assert deny["actions"] == ["s3:PutObject", "s3:PutObjectTagging", "s3:PutObjectVersionTagging"]
    assert deny["principals"][0] == {"type": "*", "identifiers": ["*"]}
    conditions = {c["variable"]: c for c in deny["condition"]}
    assert conditions["s3:RequestObjectTagKeys"]["test"] == "ForAnyValue:StringEquals"
    assert conditions["s3:RequestObjectTagKeys"]["values"] == ["GuardDutyMalwareScanStatus"]
    assert conditions["aws:PrincipalArn"]["test"] == "ArnNotEquals"
    assert conditions["aws:PrincipalArn"]["values"] == ["${aws_iam_role.malware_scan.arn}"]


def test_the_queue_key_lets_eventbridge_encrypt_messages() -> None:
    kms = {
        name: body
        for block in load("modules/kms/main.tf")["data"]
        for kind, named in block.items()
        if kind == "aws_iam_policy_document"
        for name, body in named.items()
    }
    statement = next(s for s in kms["queues"]["statement"] if s.get("sid") == "EventBridgeUse")
    assert statement["actions"] == ["kms:Decrypt", "kms:GenerateDataKey"]
    assert statement["principals"][0]["identifiers"] == ["events.amazonaws.com"]
    assert KMS["aws_kms_key.queues"]["policy"] == "${data.aws_iam_policy_document.queues.json}"


def test_scan_results_reach_an_encrypted_queue_with_a_dead_letter_queue() -> None:
    rule = PLATFORM["aws_cloudwatch_event_rule.file_scans"]
    pattern = rule["event_pattern"]
    assert '"aws.guardduty"' in pattern
    assert '"GuardDuty Malware Protection Object Scan Result"' in pattern
    assert "module.evidence.malware_protection_plan_arn" in pattern
    target = PLATFORM["aws_cloudwatch_event_target.file_scans"]
    assert target["arn"] == "${aws_sqs_queue.file_scans.arn}"
    queue, dead = PLATFORM["aws_sqs_queue.file_scans"], PLATFORM["aws_sqs_queue.file_scans_dead"]
    for q in (queue, dead):
        assert q["kms_master_key_id"] == "${module.kms.queues_key_arn}"
    assert dead["message_retention_seconds"] == 1209600  # 14 days
    assert "maxReceiveCount = 10" in queue["redrive_policy"]
    allow = PLATFORM_DOCS["file_scans_queue"]["statement"][0]
    assert allow["actions"] == ["sqs:SendMessage"]
    assert allow["principals"][0]["identifiers"] == ["events.amazonaws.com"]
    assert allow["condition"][0]["test"] == "ArnEquals"
    assert allow["condition"][0]["values"] == ["${aws_cloudwatch_event_rule.file_scans.arn}"]


def test_the_worker_may_only_drain_the_scan_queue() -> None:
    statements = {s["sid"]: s for s in ECS_POLICIES["worker"]["statement"]}
    drain = statements["DrainFileScans"]
    assert drain["actions"] == [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
    ]
    assert drain["resources"] == ["${var.file_scan_queue_arn}"]
    assert statements["FileScanKey"]["actions"] == ["kms:Decrypt"]
    assert statements["FileScanKey"]["resources"] == ["${var.queues_key_arn}"]
    platform = {k: v for m in PLATFORM_FILE["module"] for k, v in m.items()}
    assert platform["ecs"]["file_scan_queue_arn"] == "${aws_sqs_queue.file_scans.arn}"
    (environment,) = [
        b["app_environment"] for b in PLATFORM_FILE["locals"] if "app_environment" in b
    ]
    assert "ATESTA_FILE_SCAN_QUEUE_URL = aws_sqs_queue.file_scans.url" in environment


def test_the_apply_role_manages_only_malware_plans_and_its_own_queues_and_rules() -> None:
    oidc = load("modules/github-oidc/main.tf")
    apply = next(
        d["aws_iam_policy_document"]["apply"]
        for d in oidc["data"]
        if "apply" in d.get("aws_iam_policy_document", {})
    )
    statements = {s.get("sid"): s for s in apply["statement"]}
    plans = statements["MalwareProtectionPlans"]
    assert all(a.startswith("guardduty:") for a in plans["actions"])
    assert "guardduty:*" not in plans["actions"]
    assert statements["OwnQueues"]["resources"] == ["arn:aws:sqs:*:${local.account}:${var.name}-*"]
    assert statements["OwnRules"]["resources"] == [
        "arn:aws:events:*:${local.account}:rule/${var.name}-*"
    ]


# --- scan roles per customer, scan storage and the failure-rate alert (#453) ---------------

SCAN_ORG_FILE = load("modules/scan-org/main.tf")
SCAN_ORG = resources("modules/scan-org/main.tf")
SCAN_ORG_LOCALS = SCAN_ORG_FILE["locals"][0]
SCAN_ORG_VARS = {k: v for b in SCAN_ORG_FILE["variable"] for k, v in b.items()}
SCAN_ORG_DOCS = {
    name: body
    for block in SCAN_ORG_FILE["data"]
    for kind, named in block.items()
    if kind == "aws_iam_policy_document"
    for name, body in named.items()
}
ECS_LOCALS = ECS_FILE["locals"][0]


def test_scan_roles_are_per_org_bounded_and_trust_only_this_accounts_ecs_tasks() -> None:
    role = SCAN_ORG["aws_iam_role.this"]
    assert role["for_each"] == "${local.roles}"
    assert role["name"] == "${each.key}-${var.organization_id}"
    assert role["path"] == "/atesta-scan/${var.name}/"  # what the worker may pass
    assert role["permissions_boundary"] == "${var.boundary_arn}"
    (trust,) = SCAN_ORG_DOCS["trust"]["statement"]
    assert trust["actions"] == ["sts:AssumeRole"]
    assert trust["principals"] == [{"type": "Service", "identifiers": ["ecs-tasks.amazonaws.com"]}]
    conditions = {c["variable"]: c for c in trust["condition"]}
    assert conditions["aws:SourceAccount"]["values"] == ["${local.account}"]
    assert conditions["aws:SourceArn"]["test"] == "ArnLike"
    assert conditions["aws:SourceArn"]["values"] == [
        "arn:aws:ecs:${local.region}:${local.account}:*"
    ]
    assert "[0-9a-f]{8}-" in SCAN_ORG_VARS["organization_id"]["validation"][0]["condition"]
    allowed = SCAN_ORG_VARS["connectors"]["validation"][0]["condition"]
    assert 'contains(["m365", "google_workspace"], c)' in allowed


def test_each_scan_role_reads_only_its_own_credentials() -> None:
    """D7: only the verify role holds the verifier key; M365 uses the platform's one app."""
    kinds = SCAN_ORG_LOCALS["kinds"]
    assert kinds == {
        "scan-m365": {"connector": "m365", "secrets": ["${var.m365_secret_arn}"]},
        "verify-gws": {
            "connector": "google_workspace",
            "secrets": ["${local.google}", "${local.google_verifier}"],
        },
        "scan-gws": {"connector": "google_workspace", "secrets": ["${local.google}"]},
    }
    # Secrets Manager appends exactly six characters to a name; nothing else may follow.
    assert SCAN_ORG_LOCALS["google"].endswith(
        ":secret:atesta/${var.name}/google/${var.organization_id}-??????"
    )
    assert SCAN_ORG_LOCALS["google_verifier"].endswith(
        ":secret:atesta/${var.name}/google-verifier/${var.organization_id}-??????"
    )
    assert "if contains(var.connectors, role.connector)" in SCAN_ORG_LOCALS["roles"]


def test_each_scan_role_writes_outputs_and_reads_its_job_under_its_own_org_only() -> None:
    assert (
        SCAN_ORG_LOCALS["prefix"]
        == "${var.evidence_bucket_arn}/${var.organization_id}/scans/*/attempt-*"
    )
    document = SCAN_ORG_DOCS["this"]
    assert document["for_each"] == "${local.roles}"
    statements = {s["sid"]: s for s in document["statement"]}
    assert set(statements) == {"Credential", "Outputs", "Job", "SecretsKey", "EvidenceKey"}
    assert statements["Credential"]["actions"] == ["secretsmanager:GetSecretValue"]
    assert statements["Credential"]["resources"] == "${each.value}"
    assert statements["Outputs"]["actions"] == ["s3:PutObject"]
    assert statements["Outputs"]["resources"] == ["${local.prefix}/out/*"]
    assert statements["Job"]["actions"] == ["s3:GetObject"]
    assert statements["Job"]["resources"] == ["${local.prefix}/job.json"]
    for sid, key, service, actions in (
        ("SecretsKey", "secrets", "secretsmanager", ["kms:Decrypt"]),
        ("EvidenceKey", "evidence", "s3", ["kms:Decrypt", "kms:GenerateDataKey"]),
    ):
        assert statements[sid]["actions"] == actions, sid
        assert statements[sid]["resources"] == [f"${{var.{key}_key_arn}}"], sid
        (via,) = statements[sid]["condition"]
        assert (via["variable"], via["values"]) == (
            "kms:ViaService",
            [f"{service}.${{local.region}}.amazonaws.com"],
        ), sid
    policy = SCAN_ORG["aws_iam_role_policy.this"]
    assert policy["policy"] == "${data.aws_iam_policy_document.this[each.key].json}"


def test_the_owner_lists_customers_and_the_platform_creates_their_roles() -> None:
    platform = {k: v for m in PLATFORM_FILE["module"] for k, v in m.items()}
    scan_org = platform["scan_org"]
    assert scan_org["source"] == "../scan-org"
    assert scan_org["for_each"] == (
        "${var.images == null || var.edge == null ? {} : var.scan_organizations}"
    )
    assert scan_org["boundary_arn"] == "${module.ecs[0].scan_boundary_arn}"
    assert scan_org["m365_secret_arn"] == "${aws_secretsmanager_secret.m365_scanner.arn}"
    for env in ("dev", "prod"):
        assert _modules(env)["platform"]["scan_organizations"] == "${var.scan_organizations}"
        variables = {k: v for b in load(f"envs/{env}/main.tf")["variable"] for k, v in b.items()}
        assert variables["scan_organizations"]["default"] == {}


def test_the_m365_scanner_credential_is_a_hand_set_secret_under_the_scan_boundary() -> None:
    secret = PLATFORM["aws_secretsmanager_secret.m365_scanner"]
    assert secret["name"] == "atesta/${var.name}/m365/scanner"  # inside the boundary's prefix
    assert secret["kms_key_id"] == "${module.kms.secrets_key_arn}"
    assert not [k for k in PLATFORM if k.startswith("aws_secretsmanager_secret_version.")]


def test_the_scan_boundary_adds_the_evidence_key_and_only_decrypts_secrets() -> None:
    statements = {s["sid"]: s for s in ECS_POLICIES["scan_boundary"]["statement"]}
    assert set(statements) == {
        "ConnectorSecrets",
        "ScanOutputs",
        "ScanJobs",
        "SecretsKey",
        "EvidenceKey",
    }
    assert statements["SecretsKey"]["actions"] == ["kms:Decrypt"]
    assert statements["SecretsKey"]["resources"] == ["${var.secrets_key_arn}"]
    assert statements["EvidenceKey"]["actions"] == ["kms:Decrypt", "kms:GenerateDataKey"]
    assert statements["EvidenceKey"]["resources"] == ["${var.evidence_key_arn}"]


def test_scan_writers_write_once_and_scan_roles_never_delete_or_write_jobs() -> None:
    """AWS, "Enforce conditional writes on Amazon S3 buckets": a Null condition on the key."""
    locals_ = next(b for b in EVIDENCE_FILE["locals"] if "scan_roles" in b)
    assert locals_["scan_roles"].endswith(":role/atesta-scan/${var.name}/*")
    assert locals_["worker_role"].endswith(":role/${var.name}-worker")
    statements = {s.get("sid"): s for s in EVIDENCE_DOCS["bucket"]["statement"]}

    def who(statement: dict[str, Any]) -> list[str]:
        (match,) = [c for c in statement["condition"] if c["variable"] == "aws:PrincipalArn"]
        assert match["test"] == "ArnLike"
        values: list[str] = match["values"]
        return values

    once = statements["DenyScanWritesWithoutIfNoneMatch"]
    assert (once["effect"], once["actions"]) == ("Deny", ["s3:PutObject"])
    assert once["resources"] == ["${aws_s3_bucket.this.arn}/*/scans/*"]
    assert {"test": "Null", "variable": "s3:if-none-match", "values": ["true"]} in once["condition"]
    assert who(once) == ["${local.scan_roles}", "${local.worker_role}"]
    jobs = statements["DenyScanRolesJobWrites"]
    assert (jobs["effect"], jobs["actions"]) == ("Deny", ["s3:PutObject"])
    assert jobs["resources"] == ["${aws_s3_bucket.this.arn}/*/job.json"]
    assert who(jobs) == ["${local.scan_roles}"]
    metadata = statements["DenyScanRolesDeletesAndMetadata"]
    assert metadata["effect"] == "Deny"
    assert {"s3:DeleteObject", "s3:DeleteObjectVersion", "s3:PutObjectAcl"} <= set(
        metadata["actions"]
    )
    assert {"s3:PutObjectRetention", "s3:PutObjectLegalHold", "s3:PutObjectTagging"} <= set(
        metadata["actions"]
    )
    assert who(metadata) == ["${local.scan_roles}"]


def test_the_worker_writes_jobs_and_reads_and_lists_only_scan_prefixes() -> None:
    """Evidence keys carry document names, so the worker never lists the whole bucket."""
    statements = {s["sid"]: s for s in ECS_POLICIES["worker"]["statement"]}
    bucket = "${var.evidence_bucket_arn}"
    assert statements["WriteScanJobs"]["actions"] == ["s3:PutObject"]
    assert statements["WriteScanJobs"]["resources"] == [f"{bucket}/*/scans/*/attempt-*/job.json"]
    assert statements["ReadScanOutputs"]["actions"] == ["s3:GetObject"]
    assert statements["ReadScanOutputs"]["resources"] == [f"{bucket}/*/scans/*"]
    listing = statements["ListScanOutputs"]
    assert (listing["actions"], listing["resources"]) == (["s3:ListBucket"], [bucket])
    assert listing["condition"] == [
        {"test": "StringLike", "variable": "s3:prefix", "values": ["*/scans/*"]}
    ]
    key = statements["ScanStoreKey"]
    assert key["actions"] == ["kms:Decrypt", "kms:GenerateDataKey"]
    assert key["resources"] == ["${var.evidence_key_arn}"]
    s3_actions = {a for s in statements.values() for a in s["actions"] if a.startswith("s3:")}
    assert s3_actions == {"s3:PutObject", "s3:GetObject", "s3:ListBucket"}


def test_the_worker_alone_gets_every_fargate_runner_setting() -> None:
    from atesta_worker.scans import _FARGATE  # noqa: PLC0415 - the worker's own required list

    runner = ECS_LOCALS["scan_runner"]
    image_env = (INFRA.parent / "apps" / "Dockerfile").read_text()
    assert "ATESTA_SCANNER_EXPECTED=/app/scanner/expected" in image_env
    assert set(_FARGATE) - {"ATESTA_SCANNER_EXPECTED"} <= set(runner)
    assert runner["ATESTA_SCAN_RUNNER"] == "fargate"
    assert runner["ATESTA_SCAN_TASK_DEFINITION"] == "${var.name}-scan"
    assert runner["ATESTA_SCAN_ROLE_PREFIX"] == (
        "arn:aws:iam::${local.account}:role/atesta-scan/${var.name}/"
    )
    assert runner["ATESTA_M365_CREDENTIAL_REF"] == "aws-sm:${var.m365_secret_arn}"
    assert "merge(var.environment, local.scan_runner)" in CONTAINERS["worker"]
    for name in ("api", "migrate", "bootstrap"):
        assert "scan_runner" not in CONTAINERS[name], name


def test_the_scan_task_reads_its_job_from_s3_by_its_own_settings() -> None:
    environment = ECS_LOCALS["scan_environment"]
    assert {k: environment[k] for k in ("ATESTA_SCAN_SOURCE", "ATESTA_SCAN_BUCKET")} == {
        "ATESTA_SCAN_SOURCE": "s3",
        "ATESTA_SCAN_BUCKET": "${local.evidence_bucket}",
    }
    assert environment["AWS_DEFAULT_REGION"] == "${local.region}"
    assert not {k for k in environment if "SECRET" in k or "TOKEN" in k}
    assert "for k, v in local.scan_environment" in CONTAINERS["scan"]


def test_the_failure_rate_alarm_counts_scan_finished_events_and_emails_the_owner() -> None:
    """Spec: more than 5% failed over 24 h, at least 20 scans, from scan.finished events."""
    filters = ECS["aws_cloudwatch_log_metric_filter.scans"]
    assert filters["log_group_name"] == '${aws_cloudwatch_log_group.this["worker"].name}'
    assert filters["for_each"] == {
        "ScansFinished": '{ $.event = \\"scan.finished\\" }',
        "ScansFailed": '{ ($.event = \\"scan.finished\\") && ($.status = \\"failed\\") }',
    }
    alarm = ECS["aws_cloudwatch_metric_alarm.scan_failure_rate"]
    assert (alarm["comparison_operator"], alarm["threshold"]) == ("GreaterThanThreshold", 5)
    assert alarm["evaluation_periods"] == 1
    assert alarm["alarm_actions"] == ["${var.alert_topic_arn}"]
    queries = {q["id"]: q for q in alarm["metric_query"]}
    assert queries["rate"]["expression"] == (
        "IF(FILL(finished, 0) >= 20, 100 * FILL(failed, 0) / FILL(finished, 0), 0)"
    )
    for name, metric in (("finished", "ScansFinished"), ("failed", "ScansFailed")):
        (spec,) = queries[name]["metric"]
        assert (spec["metric_name"], spec["period"], spec["stat"]) == (metric, 86400, "Sum")
    topic = PLATFORM["aws_sns_topic.alerts"]
    assert topic["kms_master_key_id"] == "${module.kms.queues_key_arn}"
    subscription = PLATFORM["aws_sns_topic_subscription.alerts"]
    assert (subscription["protocol"], subscription["endpoint"]) == ("email", "${var.alert_email}")
    for env in ("dev", "prod"):
        assert _modules(env)["platform"]["alert_email"] == "${var.budget_email}"
    kms = {
        n: b
        for block in load("modules/kms/main.tf")["data"]
        for k, named in block.items()
        if k == "aws_iam_policy_document"
        for n, b in named.items()
    }
    alarms = next(s for s in kms["queues"]["statement"] if s.get("sid") == "CloudWatchAlarmsUse")
    assert alarms["principals"][0]["identifiers"] == ["cloudwatch.amazonaws.com"]
    assert alarms["actions"] == ["kms:Decrypt", "kms:GenerateDataKey*"]


# --- scan egress: Envoy proxy and VPC endpoints (#454) ---------------------------------------

WORKFLOWS = INFRA.parent / ".github" / "workflows"


def test_the_proxy_takes_connects_from_scan_tasks_only_and_sends_https_out() -> None:
    inbound = ECS["aws_vpc_security_group_ingress_rule.egress_from_scans"]
    assert inbound["security_group_id"] == "${aws_security_group.egress.id}"
    assert inbound["referenced_security_group_id"] == "${aws_security_group.scan.id}"
    assert (inbound["from_port"], inbound["to_port"]) == (3128, 3128)
    ingress = [k for k in ECS if k.startswith("aws_vpc_security_group_ingress_rule.egress")]
    assert ingress == ["aws_vpc_security_group_ingress_rule.egress_from_scans"]
    out = ECS["aws_vpc_security_group_egress_rule.egress_https"]
    assert out["security_group_id"] == "${aws_security_group.egress.id}"
    assert (out["cidr_ipv4"], out["from_port"], out["to_port"]) == ("0.0.0.0/0", 443, 443)


def test_the_proxy_runs_privately_with_no_task_role_behind_a_private_dns_name() -> None:
    task = ECS["aws_ecs_task_definition.egress"]
    assert "task_role_arn" not in task  # Envoy calls no AWS API
    assert task["execution_role_arn"] == "${aws_iam_role.scan_execution.arn}"  # pull, logs
    assert (task["cpu"], task["memory"]) == ("256", "512")
    service = ECS["aws_ecs_service.egress"]
    assert service["desired_count"] == "${var.egress_count}"
    network = service["network_configuration"][0]
    assert network["assign_public_ip"] is False
    assert network["subnets"] == "${var.private_subnet_ids}"
    assert network["security_groups"] == ["${aws_security_group.egress.id}"]
    assert service["service_registries"][0]["registry_arn"] == (
        "${aws_service_discovery_service.egress.arn}"
    )
    assert service["deployment_circuit_breaker"][0] == {"enable": True, "rollback": True}
    namespace = ECS["aws_service_discovery_private_dns_namespace.this"]
    assert (namespace["name"], namespace["vpc"]) == ("${var.name}.internal", "${var.vpc_id}")
    discovery = ECS["aws_service_discovery_service.egress"]["dns_config"][0]
    assert discovery["dns_records"] == [{"type": "A", "ttl": 10}]
    assert '"egress"' in str(ECS["aws_cloudwatch_log_group.this"]["for_each"])
    assert "var.images.egress" in CONTAINERS["egress"]
    assert "containerPort = 3128" in CONTAINERS["egress"]
    assert "secrets" not in CONTAINERS["egress"] and "environment" not in CONTAINERS["egress"]
    platform = {k: v for m in PLATFORM_FILE["module"] for k, v in m.items()}
    assert platform["ecs"]["egress_count"] == "${var.nat_per_az ? 2 : 1}"


def test_the_scan_task_goes_through_the_proxy_except_to_aws() -> None:
    environment = ECS_LOCALS["scan_environment"]
    assert environment["HTTPS_PROXY"] == (
        "http://${aws_service_discovery_service.egress.name}."
        "${aws_service_discovery_private_dns_namespace.this.name}:3128"
    )
    assert environment["NO_PROXY"] == "amazonaws.com,169.254.170.2"
    assert "HTTP_PROXY" not in environment  # the credentials endpoint is plain HTTP


def test_interface_endpoints_carry_image_pulls_logs_and_secrets() -> None:
    """AWS, "Amazon ECR interface VPC endpoints": Fargate 1.4.0+ pulls through the task's ENI."""
    endpoint = NETWORK["aws_vpc_endpoint.interface"]
    assert endpoint["for_each"] == '${toset(["ecr.api", "ecr.dkr", "logs", "secretsmanager"])}'
    assert endpoint["vpc_endpoint_type"] == "Interface"
    assert endpoint["private_dns_enabled"] is True
    assert endpoint["subnet_ids"] == "${local.endpoint_subnets}"
    assert endpoint["security_group_ids"] == ["${aws_security_group.endpoints.id}"]
    network_file = load("modules/network/main.tf")
    (subnets,) = [b["endpoint_subnets"] for b in network_file["locals"] if "endpoint_subnets" in b]
    assert subnets == "${var.nat_per_az ? aws_subnet.private[*].id : [aws_subnet.private[0].id]}"
    inbound = NETWORK["aws_vpc_security_group_ingress_rule.endpoints_https"]
    assert (inbound["cidr_ipv4"], inbound["from_port"], inbound["to_port"]) == (
        "${var.cidr}",
        443,
        443,
    )
    outputs = {k: v for b in network_file["output"] for k, v in b.items()}
    assert outputs["s3_prefix_list_id"]["value"] == "${aws_vpc_endpoint.s3.prefix_list_id}"
    assert outputs["endpoints_security_group_id"]["value"] == "${aws_security_group.endpoints.id}"


def test_every_image_variable_includes_the_egress_proxy_and_the_operator() -> None:
    expected = (
        "${object({api = string, worker = string, scan = string, egress = string,"
        " operator = string})}"
    )
    assert ECS_VARS["images"]["type"] == expected
    for path in ("modules/platform/main.tf", "envs/dev/main.tf", "envs/prod/main.tf"):
        variables = {k: v for b in load(path)["variable"] for k, v in b.items()}
        assert variables["images"]["type"] == expected, path


def test_ci_validates_the_allowlist_and_tests_it_as_ecs_runs_it() -> None:
    ci = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    steps = [s.get("run", "") for s in ci["jobs"]["images"]["steps"]]
    (proxy,) = [r for r in steps if "infra/egress/Dockerfile" in r]
    assert "--mode validate" in proxy
    assert "--read-only" in proxy and "--user 10001" in proxy and "--cap-drop ALL" in proxy
    assert 'test "$allowed" = 200' in proxy
    assert 'test "$denied" = 403' in proxy and 'test "$plain" = 403' in proxy


def test_the_deploy_builds_and_pins_the_egress_image() -> None:
    deploy = (WORKFLOWS / "deploy.yml").read_text()
    assert "docker build -f infra/egress/Dockerfile" in deploy
    assert '--arg egress "$(digest "$egress:$tag")"' in deploy
    assert "egress: $egress" in deploy


# --- operator portal (operator-portal spec, build step 6; ADR-017) ---------------------------

STAFF = resources("modules/staff-cognito/main.tf")
STAFF_POOL = STAFF["aws_cognito_user_pool.this"]
STAFF_CLIENT = STAFF["aws_cognito_user_pool_client.operator"]


def test_the_staff_pool_requires_mfa_never_by_sms_and_admits_no_self_sign_up() -> None:
    assert (STAFF_POOL["mfa_configuration"], STAFF_POOL["deletion_protection"]) == ("ON", "ACTIVE")
    assert STAFF_POOL["software_token_mfa_configuration"] == [{"enabled": True}]
    for sms in ("sms_configuration", "sms_authentication_message", "sms_verification_message"):
        assert sms not in STAFF_POOL, sms
    assert "email_mfa_configuration" not in STAFF_POOL  # TOTP or a passkey, never a mailed code
    admin_only = STAFF_POOL["admin_create_user_config"][0]
    assert admin_only["allow_admin_create_user_only"] is True
    recovery = STAFF_POOL["account_recovery_setting"][0]["recovery_mechanism"]
    assert [m["name"] for m in recovery] == ["admin_only"]
    assert STAFF_POOL["username_attributes"] == ["email"]
    assert STAFF_POOL["username_configuration"] == [{"case_sensitive": False}]


def test_staff_passkeys_require_user_verification_and_never_stand_alone() -> None:
    assert STAFF_POOL["user_pool_tier"] == "ESSENTIALS"  # passkeys need more than Lite
    assert STAFF_POOL["web_authn_configuration"] == [{"user_verification": "required"}]
    factors = STAFF_POOL["sign_in_policy"][0]["allowed_first_auth_factors"]
    # WEB_AUTHN needs another first factor (AWS); never an emailed or texted code.
    assert factors == '${var.passkeys ? ["PASSWORD", "WEB_AUTHN"] : ["PASSWORD"]}'
    flows = STAFF_CLIENT["explicit_auth_flows"]
    assert flows == (
        '${var.passkeys ? ["ALLOW_REFRESH_TOKEN_AUTH", "ALLOW_USER_AUTH"]'
        ' : ["ALLOW_REFRESH_TOKEN_AUTH"]}'
    )
    staff_vars = {
        k: v for b in load("modules/staff-cognito/main.tf")["variable"] for k, v in b.items()
    }
    assert staff_vars["passkeys"]["default"] is False  # on only after the runbook's step


def test_the_staff_invitation_is_spanish_first_with_username_and_code_once() -> None:
    es = json.loads((INFRA / "i18n/cognito.es.json").read_text())
    en = json.loads((INFRA / "i18n/cognito.en.json").read_text())
    for placeholder in ("{username}", "{####}"):
        assert es["staff_invite_message"].count(placeholder) == 1, placeholder
        assert placeholder not in en["staff_invite_message"], placeholder
    template = STAFF_POOL["admin_create_user_config"][0]["invite_message_template"][0]
    assert template["email_message"].startswith("${local.es.staff_invite_message}")


def test_the_portal_client_is_public_pkce_with_short_tokens() -> None:
    assert STAFF_CLIENT["generate_secret"] is False
    assert STAFF_CLIENT["allowed_oauth_flows"] == ["code"]
    assert STAFF_CLIENT["allowed_oauth_scopes"] == ["openid", "email"]
    assert STAFF_CLIENT["write_attributes"] and "email" not in STAFF_CLIENT["write_attributes"]
    assert STAFF_CLIENT["enable_token_revocation"] is True
    assert (STAFF_CLIENT["access_token_validity"], STAFF_CLIENT["id_token_validity"]) == (15, 15)
    assert STAFF_CLIENT["refresh_token_validity"] == 8  # hours: the session's total limit
    assert [k for k in STAFF if k.startswith("aws_cognito_user_pool_client.")] == [
        "aws_cognito_user_pool_client.operator"
    ]


def test_each_environment_has_a_staff_pool_apart_from_the_customer_pool() -> None:
    for env in ("dev", "prod"):
        modules = _modules(env)
        staff, customer = modules["staff_cognito"], modules["cognito"]
        assert staff["source"] == "../../modules/staff-cognito", env
        assert staff["name"] == f"atesta-{env}-staff" != customer["name"], env
        assert staff["domain_prefix"] != customer["domain_prefix"], env
        assert staff["passkeys"] == "${var.staff_passkeys}", env
    prod = _modules("prod")["staff_cognito"]
    assert prod["callback_urls"] == ["${var.admin_url}/auth/callback"]
    assert prod["email_sending_account"] == "DEVELOPER"  # ADR-007 amendment 1, as the customers'
    assert prod["ses_source_arn"] == "${module.ses_cognito.identity_arn}"


def test_the_operator_has_its_own_database_secret_and_session_key() -> None:
    operator = RDS["aws_secretsmanager_secret.operator_url"]
    assert operator["name"] == "atesta/${var.name}/db/operator-url"
    assert operator["kms_key_id"] == "${var.secrets_key_arn}"
    assert "aws_secretsmanager_secret_version.operator_url" not in RDS  # value set by hand
    key = PLATFORM["aws_secretsmanager_secret.operator_session_key"]
    assert key["name"] == "atesta/${var.name}/operator/session-key"
    session_key = PLATFORM["aws_secretsmanager_secret.session_key"]
    assert key["name"] != session_key["name"]
    platform = {k: v for m in PLATFORM_FILE["module"] for k, v in m.items()}
    secrets = platform["ecs"]["secrets"]
    url = "${module.database.operator_url_secret_arn}"
    assert secrets["bootstrap"]["ATESTA_OPERATOR_DATABASE_URL"] == url  # LOGIN from its URL
    for task in ("api", "worker", "migrate"):  # the customer side never holds it
        assert url not in secrets[task].values(), task


OPERATOR = resources("modules/ecs/operator.tf")
OPERATOR_FILE = load("modules/ecs/operator.tf")
OPERATOR_POLICIES = {
    name: body
    for block in OPERATOR_FILE["data"]
    for kind, named in block.items()
    if kind == "aws_iam_policy_document"
    for name, body in named.items()
}


def test_the_operator_task_role_may_only_read_the_staff_pool_mfa_settings() -> None:
    (statement,) = OPERATOR_POLICIES["operator"]["statement"]
    assert statement["actions"] == ["cognito-idp:GetUserPoolMfaConfig"]
    assert statement["resources"] == ["${var.operator.staff_pool_arn}"]
    task = OPERATOR["aws_ecs_task_definition.operator"]
    assert task["task_role_arn"] == "${aws_iam_role.operator.arn}"
    assert task["execution_role_arn"] == "${aws_iam_role.operator_execution.arn}"
    attached = [k for k in OPERATOR if k.startswith("aws_iam_role_policy_attachment.")]
    assert attached == ["aws_iam_role_policy_attachment.operator_execution_managed"]


def test_only_the_operator_execution_role_reads_the_operator_secrets() -> None:
    read = OPERATOR_POLICIES["operator_execution"]["statement"][0]
    assert read["resources"] == "${local.operator_secret_arns}"
    assert "var.secrets.operator" in OPERATOR_FILE["locals"][0]["operator_secret_arns"]
    shared = ECS_FILE["locals"][0]["secret_arns"]
    assert "var.secrets.operator" not in shared  # the API, worker and migrate role never can
    container = CONTAINERS["operator"]
    assert "secrets = [for k, arn in var.secrets.operator :" in container
    assert "var.environment" not in container  # never the API's settings
    platform = {k: v for m in PLATFORM_FILE["module"] for k, v in m.items()}
    operator_secrets = platform["ecs"]["secrets"]["operator"]
    assert set(operator_secrets) == {"ATESTA_OPERATOR_DATABASE_URL", "ATESTA_OPERATOR_SESSION_KEY"}
    session_key = "${aws_secretsmanager_secret.session_key.arn}"
    assert session_key not in operator_secrets.values()  # the console's key stays the API's
    rule = OPERATOR_FILE["variable"][0]["operator"]["validation"][0]["condition"]
    assert "DATABASE_URL|_KEY|SECRET|PASSWORD|TOKEN" in rule


def test_the_operator_runs_privately_and_takes_traffic_only_from_the_load_balancer() -> None:
    service = OPERATOR["aws_ecs_service.operator"]
    network = service["network_configuration"][0]
    assert network["assign_public_ip"] is False
    assert network["subnets"] == "${var.private_subnet_ids}"
    assert network["security_groups"] == ["${aws_security_group.operator.id}"]
    assert service["deployment_circuit_breaker"][0] == {"enable": True, "rollback": True}
    assert service["load_balancer"][0]["container_port"] == 8001
    ingress = {k: v for k, v in OPERATOR.items() if k.startswith("aws_vpc_security_group_ingress")}
    assert set(ingress) == {
        "aws_vpc_security_group_ingress_rule.operator_from_alb",
        "aws_vpc_security_group_ingress_rule.db_from_operator",
    }
    from_alb = ingress["aws_vpc_security_group_ingress_rule.operator_from_alb"]
    assert from_alb["referenced_security_group_id"] == "${aws_security_group.alb.id}"
    assert all("cidr_ipv4" not in rule for rule in ingress.values())
    assert OPERATOR["aws_lb_target_group.operator"]["health_check"][0]["path"] == "/health"


def test_only_the_admin_distributions_header_reaches_the_operator() -> None:
    rule = OPERATOR["aws_lb_listener_rule.operator"]
    header = rule["condition"][0]["http_header"][0]
    assert header == {
        "http_header_name": "${local.operator_header}",
        "values": ["${var.operator_origin_header}"],
    }
    assert rule["action"][0]["target_group_arn"] == "${aws_lb_target_group.operator.arn}"
    variable = OPERATOR_FILE["variable"][1]["operator_origin_header"]
    assert variable["sensitive"] is True
    secret = PLATFORM["aws_secretsmanager_secret.operator_origin_header"]
    assert secret["name"] == "atesta/${var.name}/operator/origin-header"
    assert "aws_secretsmanager_secret_version.operator_origin_header" not in PLATFORM  # by hand
    # The API's default action is unchanged: no header, no operator.
    assert EDGE["aws_lb_listener.https"]["default_action"][0]["target_group_arn"] == (
        "${aws_lb_target_group.api.arn}"
    )


def test_the_deploy_builds_and_pins_the_operator_image() -> None:
    deploy = (WORKFLOWS / "deploy.yml").read_text()
    assert "for target in api worker operator; do" in deploy
    assert "operator: $operator" in deploy
    assert ".edge.admin_aliases[0]" in deploy
