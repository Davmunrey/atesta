# Atesta scan runner (scanner-connectors spec, Scanner image and wrapper; ADR-002, ADR-004).
# Build from the repository root: docker build -f scanner/Dockerfile -t atesta-scanner .
# The base image and PowerShell pins are the ones Prowler 5.52.0's own image uses (its Dockerfile
# is unchanged since 5.49.0): https://raw.githubusercontent.com/prowler-cloud/prowler/5.52.0/Dockerfile
FROM python:3.12.16-slim-trixie@sha256:8523d6abeb48ceae0b7240d30c5808fc26cb79c1a635bacdf19cf3baecfbec07

ARG POWERSHELL_VERSION=7.6.10
ARG POWERSHELL_SHA256=e261cabc91c78a9afe8d1e5f24731ab0d38204735ab2ec94b0af55102652e10d
ENV POWERSHELL_TELEMETRY_OPTOUT=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# PowerShell's native runtime on Debian 13 (without ICU, .NET does not start). No PowerShell
# modules: Exchange and Teams arrive with PR 10 (D1, D11); MSAL.PS is never installed.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libicu76 libunwind8 libssl3 libcurl4 ca-certificates curl \
 && curl -fsSL --proto '=https' -o /tmp/powershell.tar.gz \
      "https://github.com/PowerShell/PowerShell/releases/download/v${POWERSHELL_VERSION}/powershell-${POWERSHELL_VERSION}-linux-x64.tar.gz" \
 && echo "${POWERSHELL_SHA256}  /tmp/powershell.tar.gz" | sha256sum -c - \
 && mkdir -p /opt/microsoft/powershell/7 \
 && tar -xzf /tmp/powershell.tar.gz -C /opt/microsoft/powershell/7 \
 && chmod +x /opt/microsoft/powershell/7/pwsh \
 && ln -s /opt/microsoft/powershell/7/pwsh /usr/bin/pwsh \
 && rm /tmp/powershell.tar.gz \
 && apt-get purge -y --auto-remove curl \
 && rm -rf /var/lib/apt/lists/*

# Prowler and every dependency, hash-locked. The sdist-only ones build with the hash-locked
# setuptools, never with a tool fetched at build time. Nothing is installed at scan time.
COPY scanner/build-requirements.txt scanner/requirements.txt /tmp/
RUN pip install --no-cache-dir --require-hashes -r /tmp/build-requirements.txt \
 && pip install --no-cache-dir --require-hashes --no-deps --no-build-isolation \
      -r /tmp/requirements.txt \
 && rm /tmp/build-requirements.txt /tmp/requirements.txt

# The wrapper, its pure-logic dependency and the expected lists.
COPY packages/core/src/atesta_core /opt/atesta/atesta_core
COPY scanner/atesta_scanner /opt/atesta/atesta_scanner
COPY scanner/expected /opt/atesta/expected
ENV PYTHONPATH=/opt/atesta
RUN printf '#!/bin/sh\nexec python -m atesta_scanner "$@"\n' > /usr/local/bin/atesta-scan \
 && chmod 755 /usr/local/bin/atesta-scan \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin scanner

USER 10001
WORKDIR /work
ENTRYPOINT ["atesta-scan"]
