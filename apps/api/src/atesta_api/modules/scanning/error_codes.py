"""Codes a scan stores in error_code (#270). GET /scans returns them, so the contract export
lists them and the web holds ES and EN text for each one. The model refuses any other code."""

TRANSIENT_ERRORS = {21: "scanning.timeout", 30: "scanning.output_invalid"}
ENGINE_FAILED = "scanning.engine_failed"  # 11, 12, 20 and any code the wrapper never returns
BLOCKED_CODES = {
    "incomplete": "connections.incomplete_permissions",
    "over_privileged": "connections.over_privileged",
    "revoked": "connections.revoked",
}
CONNECTION_NOT_ACTIVE = "scanning.connection_not_active"
TENANT_MISMATCH = "scanning.tenant_mismatch"
OUTPUT_INVALID = TRANSIENT_ERRORS[30]

SCAN_ERROR_CODES = frozenset(
    {
        *TRANSIENT_ERRORS.values(),
        ENGINE_FAILED,
        *BLOCKED_CODES.values(),
        CONNECTION_NOT_ACTIVE,
        TENANT_MISMATCH,
    }
)
