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
