# Scan runner image (ADR-002, ADR-004).
# One ephemeral container per scan: assumes the tenant's read-only credentials,
# runs Prowler, writes OCSF JSON to the tenant's S3 prefix, exits.
FROM python:3.12-slim

# Pinned. Bump only via PR with golden-test run against the new version.
ARG PROWLER_VERSION=5.49.0
RUN pip install --no-cache-dir "prowler==${PROWLER_VERSION}"

RUN useradd --create-home --uid 10001 scanner
USER scanner
WORKDIR /home/scanner

# Atesta custom checks and ENS mappings for M365 / Google Workspace are added here (Phase 2).
# COPY --chown=scanner custom_checks/ ./custom_checks/

ENTRYPOINT ["prowler"]
