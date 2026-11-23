"""Static checks of the OpenTofu code (infra-dev spec): no AWS credentials needed.

Each assertion pins a setting the identity spec requires; several cannot change after the pool
exists (username attributes, case sensitivity), so a drift must fail before any apply.
"""

import json
from pathlib import Path
from typing import Any

import hcl2

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
    deny = next(
        b["aws_iam_policy_document"]["tls_only"] for b in policy if "aws_iam_policy_document" in b
    )
    statement = deny["statement"][0]
    assert (
        statement["effect"] == "Deny"
        and statement["condition"][0]["variable"] == "aws:SecureTransport"
    )


def test_private_subnets_take_no_public_addresses_and_flow_logs_are_on() -> None:
    for kind in ("public", "private"):
        assert NETWORK[f"aws_subnet.{kind}"]["map_public_ip_on_launch"] is False
    private_routes = NETWORK["aws_route_table.private"]["route"][0]
    assert "nat_gateway_id" in private_routes and "gateway_id" not in private_routes
    assert NETWORK["aws_flow_log.this"]["traffic_type"] == "ALL"
    assert "kms_key_id" in NETWORK["aws_cloudwatch_log_group.flow"]


RDS = resources("modules/rds/main.tf")
RDS_VARS = {k: v for b in load("modules/rds/main.tf")["variable"] for k, v in b.items()}


def test_the_database_is_postgres_16_encrypted_private_and_protected() -> None:
    db = RDS["aws_db_instance.this"]
    assert (db["engine"], db["engine_version"]) == ("postgres", "16")
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
    assert RDS["aws_cloudwatch_log_group.postgres"]["kms_key_id"] == "${var.logs_key_arn}"
    assert "retention_in_days" in RDS["aws_cloudwatch_log_group.postgres"]


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


def test_dev_wires_the_database_and_optional_notification_email() -> None:
    dev = load("envs/dev/main.tf")
    modules = {k: v for m in dev["module"] for k, v in m.items()}
    assert "providers" not in modules["ses_notifications"]  # eu-south-2, not the Paris exception
    assert modules["ses_notifications"]["count"] == "${var.mail_domain == null ? 0 : 1}"
    database = modules["database"]
    assert database["backup_retention_days"] == 14 and database["multi_az"] is False
    assert database["kms_key_arn"] == "${module.kms.database_key_arn}"


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
    assert set(CONTAINERS) == {"api", "worker", "migrate", "scan"}
    for name, container in CONTAINERS.items():
        assert container.startswith("${merge(local.locked, {"), name
        assert 'logDriver = "awslogs"' in container, name
        assert f'aws_cloudwatch_log_group.this["{name}"].name' in container, name


def test_secrets_come_only_from_secrets_manager_never_from_plain_environment() -> None:
    for name in ("api", "worker", "migrate"):
        assert f"secrets = [for k, arn in var.secrets.{name} :" in CONTAINERS[name], name
    assert (
        "secrets" not in CONTAINERS["scan"]
    )  # the wrapper reads its credential with the task role
    rule = ECS_VARS["environment"]["validation"][0]["condition"]
    assert "DATABASE_URL|_KEY|SECRET|PASSWORD|TOKEN" in rule
    exec_policy = ECS_POLICIES["execution"]["statement"]
    read = next(s for s in exec_policy if "secretsmanager:GetSecretValue" in s["actions"])
    assert "*" not in str(read["resources"])


def test_images_are_pinned_by_digest_and_registries_are_immutable() -> None:
    rule = ECS_VARS["images"]["validation"][0]["condition"]
    assert "@sha256:[0-9a-f]{64}$" in rule
    repos = resources("modules/ecr/main.tf")["aws_ecr_repository.this"]
    assert repos["for_each"] == '${toset(["api", "worker", "scan"])}'
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


def test_one_scan_task_definition_with_no_baked_role_and_https_only_egress() -> None:
    scan = ECS["aws_ecs_task_definition.scan"]
    assert "task_role_arn" not in scan  # ADR-004: the worker passes the per-org role per run
    assert (scan["cpu"], scan["memory"]) == ("2048", "4096")  # scanner-connectors D13
    egress = [k for k in ECS if k.startswith("aws_vpc_security_group_egress_rule.scan")]
    assert egress == ["aws_vpc_security_group_egress_rule.scan_https"]
    assert ECS["aws_vpc_security_group_egress_rule.scan_https"]["from_port"] == 443
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
    assert set(behaviors) == {"/api/*", "/auth/*", "/invite*", "/training*"}
    assert "custom_error_response" not in dist  # would rewrite the API's own error responses
    for path in ("/api/*", "/auth/*"):
        assert behaviors[path]["target_origin_id"] == "api", path
        assert behaviors[path]["viewer_protocol_policy"] == "https-only", path
    for path in ("/invite*", "/training*"):
        policy = behaviors[path]["response_headers_policy_id"]
        assert policy == "${aws_cloudfront_response_headers_policy.no_referrer.id}", path
    assert dist["viewer_certificate"][0]["minimum_protocol_version"] == "TLSv1.2_2021"
    assert dist["viewer_certificate"][0]["ssl_support_method"] == "sni-only"
    api = next(o for o in dist["origin"] if o["origin_id"] == "api")
    origin = api["custom_origin_config"][0]
    assert origin["origin_protocol_policy"] == "https-only"
    assert origin["origin_ssl_protocols"] == ["TLSv1.2"]
